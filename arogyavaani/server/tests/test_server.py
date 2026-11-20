"""Server wiring: config, start/stop, language swap, nurse speak, proactive call accept, console, demo, ws."""
import pytest
from fastapi.testclient import TestClient

import db
from events import hub
from tests.conftest import next_weekday_date


@pytest.fixture
def srv(monkeypatch):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    import server
    started = []

    async def fake_start(sid, channel, agent_uid, user_uid, lang, patient_id, elder, greeting=None, codec=None):
        started.append(dict(sid=sid, channel=channel, lang=lang, patient=patient_id, elder=elder, greeting=greeting))
        server.manager.live[sid] = {"session": FakeSess(), "agent_id": "ag-" + sid, "channel": channel,
                                    "agent_uid": agent_uid, "user_uid": user_uid, "lang": lang, "elder": elder,
                                    "patient_id": patient_id}
        return {"agent_id": "ag-" + sid, "channel_name": channel, "status": "started", "lang": lang, "session_id": sid}
    monkeypatch.setattr(server.manager, "start", fake_start)
    server.manager.live.clear()
    with TestClient(server.app) as c:
        c.started = started
        c.server = server
        yield c


class FakeSess:
    def __init__(self):
        self.said, self.stopped = [], False

    async def say(self, text, priority=None):
        self.said.append((text, priority))

    async def stop(self):
        self.stopped = True


def start(c, **kw):
    body = {"channelName": "ch1", "rtcUid": 1111, "userUid": 2222, "sessionId": "sx", **kw}
    r = c.post("/session/start", json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_get_config_has_token_and_session(srv):
    r = srv.get("/get_config", params={"patient": "lakshmi"})
    d = r.json()["data"]
    assert r.status_code == 200 and d["token"] and d["session_id"] and d["patient_id"] == "lakshmi"


def test_start_uses_profile_language_and_named_greeting(srv):
    srv.post("/demo/seed")
    db.upsert_patient("lakshmi", preferred_lang="kn-IN")
    start(srv, patientId="lakshmi")
    s = srv.started[-1]
    assert s["lang"] == "kn-IN" and "Lakshmi" in s["greeting"]
    assert db.get_call_session("sx").stage == "BEFORE"


def test_legacy_start_stop_contract(srv):
    r = srv.post("/startAgent", json={"channelName": "c", "rtcUid": 5, "userUid": 6})
    assert r.json()["code"] == 0
    aid = r.json()["data"]["agent_id"]
    assert srv.post("/stopAgent", json={"agentId": aid}).json()["code"] == 0
    assert not srv.server.manager.live


def test_start_validation_error_is_400(srv):
    assert srv.post("/startAgent", json={"channelName": "c"}).status_code == 422


def test_language_route_calls_hot_swap(srv, monkeypatch):
    start(srv)
    calls = []

    async def fake_swap(sid, lang):
        calls.append((sid, lang))
        return {"ok": True, "swapped": True, "lang": lang, "ms": 1800}
    monkeypatch.setattr(srv.server.manager, "hot_swap", fake_swap)
    r = srv.post("/session/sx/language", json={"lang": "kn-IN"})
    assert r.json()["data"]["ms"] == 1800 and calls == [("sx", "kn-IN")]


def test_nurse_speak_requires_password_and_logs(srv, monkeypatch):
    monkeypatch.setenv("CONSOLE_PASSWORD", "nurse")
    start(srv)
    assert srv.post("/session/sx/speak", json={"text": "hi"}).status_code == 401
    r = srv.post("/session/sx/speak", json={"text": "Nurse here, stay calm.", "priority": "INTERRUPT"},
                 headers={"X-Console-Password": "nurse"})
    assert r.status_code == 200 and srv.server.manager.live["sx"]["session"].said == [("Nurse here, stay calm.", "INTERRUPT")]
    assert any(e["type"] == "nurse_speak" for e in hub.recent("sx"))
    assert srv.get("/console/sessions").status_code == 401
    cs = srv.get("/console/sessions", headers={"X-Console-Password": "nurse"}).json()
    assert cs["sessions"][0]["id"] == "sx"


def test_speak_without_live_agent_is_400(srv):
    assert srv.post("/session/ghost/speak", json={"text": "hello"}).status_code == 400


def test_resolve_escalation(srv):
    db.update_call_session("sx", escalated=True, stage="ESCALATED")
    assert srv.post("/console/sx/resolve").json()["ok"]
    assert db.get_call_session("sx").escalated is False


def test_demo_reset_seeds_lakshmi_and_clears_bookings(srv):
    with db.session() as s:
        s.add(db.Booking(id="BKX", hold_id="h", doctor_id="doc01", date="2030-01-01", time="10:00", patient_id="p", idempotency_key="z"))
        s.commit()
    r = srv.post("/demo/reset")
    assert r.json()["patient_id"] == "lakshmi" and db.get_patient("lakshmi").name == "Lakshmi"
    with db.session() as s:
        assert s.get(db.Booking, "BKX") is None


def test_demo_disabled_hides_controls(srv, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")
    assert srv.post("/demo/reset").status_code == 404


def _booked(srv):
    from tools import handlers  # noqa: F401
    db.upsert_patient("lakshmi", name="Lakshmi", preferred_lang="hi-IN", languages="kn,hi")
    date = next_weekday_date()
    with db.session() as s:
        s.add(db.Booking(id="BKR", hold_id="h", doctor_id="doc01", date=date, time="10:30", patient_id="lakshmi", idempotency_key="r"))
        s.commit()
    import scheduler
    scheduler.schedule_for_booking({"booking_id": "BKR", "date": date, "time": "10:30"}, "lakshmi")


def test_fast_forward_then_accept_starts_agent_that_speaks_first(srv):
    _booked(srv)
    ff = srv.post("/demo/fast-forward/BKR").json()["fired"]
    assert ff["kind"] == "reminder"
    ev = [e for e in hub.recent("patient:lakshmi") if e["type"] == "incoming_call"][-1]
    r = srv.post("/call/accept", json={"followupId": ev["followup_id"], "channelName": "ch2", "rtcUid": 7, "userUid": 8, "sessionId": "after1"})
    assert r.status_code == 200, r.text
    s = srv.started[-1]
    assert "Dr. Suresh Rao" in s["greeting"] and "Lakshmi" in s["greeting"]
    cs = db.get_call_session("after1")
    assert cs.stage == "AFTER" and "reminder" in cs.note and cs.summary.startswith("BKR|doc01")


def test_feedback_call_context(srv):
    _booked(srv)
    srv.post("/demo/fast-forward/BKR")
    ff2 = srv.post("/demo/fast-forward/BKR").json()["fired"]
    assert ff2["kind"] == "feedback"
    r = srv.post("/call/accept", json={"followupId": ff2["followup_id"], "channelName": "ch3", "rtcUid": 7, "userUid": 8, "sessionId": "after2"})
    assert r.status_code == 200
    assert "record_feedback" in db.get_call_session("after2").note


def test_healthz(srv):
    j = srv.get("/healthz").json()
    assert j["checks"]["db"] == "ok" and j["status"] == "ok"


def test_ws_events_replay_and_live(srv):
    hub.publish("wsx", {"type": "stage", "stage": "DURING"})
    with srv.websocket_connect("/ws/events/wsx") as ws:
        assert ws.receive_json()["stage"] == "DURING"
        hub.publish("wsx", {"type": "tool_end", "tool": "x"})
        assert ws.receive_json()["tool"] == "x"


def test_inbox_and_events_endpoints(srv):
    with db.session() as s:
        s.add(db.InboxMessage(patient_id="lakshmi", text="hello"))
        s.commit()
    assert srv.get("/inbox/lakshmi").json()["messages"][0]["text"] == "hello"
    hub.publish("ev1", {"type": "x"})
    assert srv.get("/events/ev1").json()["events"]


def test_static_and_clinic_mounted(srv):
    assert srv.get("/clinic/v1/slots", params={"doctor_id": "doc01", "date": next_weekday_date()}).status_code == 200
    assert srv.get("/llm/health").json()["status"] == "ok"
    assert "openapi" in srv.get("/openapi.json").json()


def test_elder_toggle_restarts_live_agent(srv, monkeypatch):
    start(srv, patientId="lakshmi")
    calls = []

    async def fake_swap(sid, lang, force=False):
        calls.append((sid, lang, force))
        return {"ok": True, "swapped": True}
    monkeypatch.setattr(srv.server.manager, "hot_swap", fake_swap)
    r = srv.post("/session/sx/elder", params={"on": "true"}).json()
    assert r["restarted"] and calls == [("sx", "hi-IN", True)]
    assert db.get_patient("lakshmi").elder_mode is True
