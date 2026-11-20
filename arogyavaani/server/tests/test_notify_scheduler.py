"""Message templates (hi/kn/en), ICS, Murf voice note, Twilio fallback, follow-up scheduling."""
import httpx
import pytest

import db
import directory
import i18n
import notify
import scheduler
from events import hub
from tests.conftest import next_weekday_date

BOOKING = {"booking_id": "BK123", "doctor_id": "doc01", "date": next_weekday_date(), "time": "10:30", "status": "confirmed"}
DOC = directory.get_doctor("doc01")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_confirmation_templates(lang):
    msg = notify.build_confirmation(BOOKING, DOC, "Lakshmi", lang)
    assert "BK123" in msg and "Dr. Suresh Rao" in msg and "{" not in msg
    cg = notify.build_confirmation(BOOKING, DOC, "Lakshmi", lang, caregiver=True)
    assert "Lakshmi" in cg and "BK123" in cg


def test_language_specific_script():
    assert any("ऀ" <= ch <= "ॿ" for ch in notify.build_confirmation(BOOKING, DOC, "L", "hi-IN"))
    assert any("ಀ" <= ch <= "೿" for ch in notify.build_confirmation(BOOKING, DOC, "L", "kn-IN"))


def test_ics_valid():
    ics = notify.make_ics(BOOKING, DOC)
    assert ics.startswith("BEGIN:VCALENDAR") and "BK123@arogyavaani" in ics and "DTSTART;TZID=Asia/Kolkata" in ics


async def test_voice_note_none_without_key():
    assert await notify.generate_voice_note("hi", "hi-IN", "BK1") is None


async def test_voice_note_calls_murf_and_caches(monkeypatch):
    monkeypatch.setenv("MURF_API_KEY", "mk")
    monkeypatch.setenv("MURF_VOICE_ID", "Neeta")
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, content=b"ID3fakeaudio")
    import http_util
    http_util.set_transport(httpx.MockTransport(handler))
    url = await notify.generate_voice_note("आपका appointment confirm है", "hi-IN", "BK9")
    again = await notify.generate_voice_note("आपका appointment confirm है", "hi-IN", "BK9")
    assert url == again and url.startswith("/static/voice/BK9-") and len(seen) == 1  # cached by text hash
    req = seen[0]
    assert req.url.path == "/v1/speech/stream" and req.headers["api-key"] == "mk"
    import json
    body = json.loads(req.content)
    assert body["model"] == "FALCON" and body["locale"] == "hi-IN" and body["voiceId"] == "Neeta" and body["format"] == "MP3"


async def test_twilio_failure_falls_back_to_inbox(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC1")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "t")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    import http_util
    http_util.set_transport(httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    res = await notify.deliver("p1", "patient", "+919999999999", "hello")
    assert res["channel"] == "inbox" and res["delivered"] is False
    with db.session() as s:
        assert s.exec(db.select(db.InboxMessage) if hasattr(db, "select") else __import__("sqlmodel").select(db.InboxMessage)).all()


async def test_twilio_success_marks_whatsapp(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC1")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "t")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    import http_util
    http_util.set_transport(httpx.MockTransport(lambda r: httpx.Response(201, json={"sid": "SM1"})))
    res = await notify.deliver("p1", "patient", "+919999999999", "hello", media_path="/static/voice/x.mp3")
    assert res["channel"] == "whatsapp" and res["delivered"]


async def test_schedule_and_fast_forward_pushes_incoming_call():
    db.upsert_patient("p1", name="Lakshmi", preferred_lang="kn-IN")
    with db.session() as s:
        s.add(db.Booking(id="BK123", hold_id="h", doctor_id="doc01", date=BOOKING["date"], time="10:30",
                         patient_id="p1", idempotency_key="k"))
        s.commit()
    jobs = scheduler.schedule_for_booking(BOOKING, "p1")
    assert [j["kind"] for j in jobs] == ["reminder", "feedback"]
    assert scheduler.schedule_for_booking(BOOKING, "p1")[0]["id"] == jobs[0]["id"]  # idempotent
    p1 = await scheduler.fast_forward("BK123")
    assert p1["kind"] == "reminder" and p1["lang"] == "kn-IN" and p1["doctor"] == "Dr. Suresh Rao"
    assert any(e["type"] == "incoming_call" for e in hub.recent("patient:p1"))
    p2 = await scheduler.fast_forward("BK123")
    assert p2["kind"] == "feedback"
    assert await scheduler.fast_forward("BK123") is None
    assert await scheduler.fire(jobs[0]["id"]) is None  # already fired


def test_reminder_is_12h_before_and_feedback_2h_after():
    slot = scheduler.slot_epoch("2099-01-02", "10:30")
    assert slot - scheduler.REMINDER_BEFORE_S == scheduler.slot_epoch("2099-01-01", "22:30")
    assert scheduler.FEEDBACK_AFTER_S == 7200
