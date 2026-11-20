import time

import httpx
import pytest

from tests.conftest import next_weekday_date

DOC = "doc01"  # Dr. Suresh Rao, orthopaedics, Mon-Sat 09:00-13:00


@pytest.fixture
async def c(clinic_transport):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=clinic_transport), base_url="http://t/clinic/v1") as client:
        yield client


async def hold(c, t="10:00", date=None):
    return await c.post("/holds", json={"doctor_id": DOC, "date": date or next_weekday_date(), "time": t, "patient_id": "p"})


async def test_slots_listed(c):
    r = await c.get("/slots", params={"doctor_id": DOC, "date": next_weekday_date()})
    assert r.status_code == 200 and "10:00" in r.json()["slots"]


async def test_second_hold_conflicts(c):
    assert (await hold(c)).status_code == 201
    assert (await hold(c)).status_code == 409


async def test_held_slot_disappears_from_availability(c):
    d = next_weekday_date()
    await hold(c, "10:00", d)
    slots = (await c.get("/slots", params={"doctor_id": DOC, "date": d})).json()["slots"]
    assert "10:00" not in slots


async def test_idempotent_confirm_returns_same_booking(c):
    h = (await hold(c)).json()
    b1 = await c.post("/bookings", json={"hold_id": h["hold_id"], "idempotency_key": "k1"})
    b2 = await c.post("/bookings", json={"hold_id": h["hold_id"], "idempotency_key": "k1"})
    assert b1.status_code == 201 and b2.json()["booking_id"] == b1.json()["booking_id"]


async def test_hold_expiry_frees_slot_and_rejects_confirm(c, monkeypatch):
    monkeypatch.setenv("HOLD_TTL_S", "0")
    h = (await hold(c)).json()
    time.sleep(0.05)
    r = await c.post("/bookings", json={"hold_id": h["hold_id"], "idempotency_key": "k2"})
    assert r.status_code == 410
    assert (await hold(c)).status_code == 201  # slot is free again


async def test_cancel_frees_slot(c):
    h = (await hold(c)).json()
    b = (await c.post("/bookings", json={"hold_id": h["hold_id"], "idempotency_key": "k3"})).json()
    assert (await hold(c)).status_code == 409
    assert (await c.delete(f"/bookings/{b['booking_id']}")).status_code == 200
    assert (await hold(c)).status_code == 201


async def test_force_conflict_toggle(c):
    await c.post("/admin/force-conflict")
    assert (await hold(c, "10:30")).status_code == 409
    assert (await hold(c, "11:00")).status_code == 201  # toggle is one-shot


async def test_invalid_slot_and_doctor(c):
    assert (await hold(c, "03:00")).status_code == 422
    r = await c.post("/holds", json={"doctor_id": "nope", "date": next_weekday_date(), "time": "10:00"})
    assert r.status_code == 404
