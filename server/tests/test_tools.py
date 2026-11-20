import json

import db
from tests.conftest import next_weekday_date
from tools import handlers
from tools.registry import REGISTRY, run_tool, schemas

DATE = next_weekday_date()


def test_registry_has_all_tools():
    names = set(REGISTRY)
    assert {"get_patient_profile", "save_patient_profile", "triage_symptoms", "search_doctors", "check_availability",
            "hold_slot", "confirm_booking", "cancel_booking", "send_confirmation", "generate_voice_note",
            "schedule_followup", "record_feedback", "escalate_to_human", "set_language", "search_knowledge"} <= names
    for s in schemas():
        json.dumps(s)
        assert s["function"]["parameters"]["type"] == "object"


def test_ranking_prefers_language_match():
    docs = handlers.rank_doctors("orthopaedics", "Jayanagar", ["kn", "hi"])
    assert docs[0]["language_match"], docs
    assert docs[0]["id"] == "doc01"  # kn+hi speaker, closest, PM-JAY
    only_ml = handlers.rank_doctors("orthopaedics", "Jayanagar", ["ml"])
    assert all(not d["language_match"] for d in only_ml)


async def test_full_booking_flow_and_idempotent_confirm(ctx):
    r = await run_tool(ctx, "search_doctors", {"specialty": "orthopaedics"})
    assert len(r["doctors"]) == 3
    r = await run_tool(ctx, "check_availability", {"doctor_id": "doc01", "date": DATE})
    assert "10:00" in r["slots"]
    h = await run_tool(ctx, "hold_slot", {"doctor_id": "doc01", "date": DATE, "time": "10:00"})
    assert h["ok"] and h["hold_id"]
    b1 = await run_tool(ctx, "confirm_booking", {"hold_id": h["hold_id"]})
    b2 = await run_tool(ctx, "confirm_booking", {"hold_id": h["hold_id"]})
    assert b1["ok"] and b1["booking_id"] == b2["booking_id"]
    assert db.get_call_session("s1").stage == "CONFIRM"


async def test_conflict_returns_two_alternatives(ctx):
    import clinic_api
    clinic_api._force_conflict["next"] = True
    h = await run_tool(ctx, "hold_slot", {"doctor_id": "doc01", "date": DATE, "time": "10:00"})
    assert h["conflict"] and len(h["alternatives"]) == 2 and "10:00" not in h["alternatives"]


async def test_triage_red_flag_escalates_and_blocks_booking(ctx):
    r = await run_tool(ctx, "triage_symptoms", {"symptoms": "seene mein dard"})
    assert r["red_flag"] and db.get_call_session("s1").escalated
    h = await run_tool(ctx, "hold_slot", {"doctor_id": "doc01", "date": DATE, "time": "10:00"})
    assert h["ok"] is False


async def test_bad_args_and_unknown_tool_do_not_crash(ctx):
    assert (await run_tool(ctx, "nope", {}))["ok"] is False
    assert (await run_tool(ctx, "hold_slot", {"bogus": 1}))["ok"] is False


async def test_send_confirmation_writes_inbox_and_ics(ctx):
    db.upsert_patient("p1", caregiver_phone="+910000000000")
    h = await run_tool(ctx, "hold_slot", {"doctor_id": "doc01", "date": DATE, "time": "09:30"})
    b = await run_tool(ctx, "confirm_booking", {"hold_id": h["hold_id"]})
    r = await run_tool(ctx, "send_confirmation", {"booking_id": b["booking_id"]})
    assert r["ok"] and {m["recipient"] for m in r["messages"]} == {"patient", "caregiver"}
    assert r["ics"].endswith(".ics") and r["voice_note"] is None  # no MURF key in tests
    assert all(m["channel"] == "inbox" for m in r["messages"])  # Twilio absent -> inbox fallback


async def test_schedule_followup_and_feedback(ctx):
    h = await run_tool(ctx, "hold_slot", {"doctor_id": "doc01", "date": DATE, "time": "09:00"})
    b = await run_tool(ctx, "confirm_booking", {"hold_id": h["hold_id"]})
    s = await run_tool(ctx, "schedule_followup", {"booking_id": b["booking_id"]})
    assert [j["kind"] for j in s["jobs"]] == ["reminder", "feedback"]
    f = await run_tool(ctx, "record_feedback", {"booking_id": b["booking_id"], "rating": 9})
    assert f["rating"] == 5


async def test_set_language_queues_swap(ctx):
    r = await run_tool(ctx, "set_language", {"language": "Kannada"})
    assert r["language"] == "kn-IN" and handlers.PENDING_SWAPS["s1"] == "kn-IN"


async def test_search_knowledge(ctx):
    r = await run_tool(ctx, "search_knowledge", {"query": "sugar test ke liye kya karna hai fasting"})
    assert r["results"] and "fast" in r["results"][0]["text"].lower()
