"""Mock Clinic Booking API (/clinic/v1): an external-looking service with transaction-grade booking.

- GET  /slots?doctor_id&date                  open slots
- POST /holds                                 120 s TTL hold, 409 if the slot is taken
- POST /bookings {hold_id, idempotency_key}   confirm; same key -> same booking
- DELETE /bookings/{id}                       cancel (frees the slot)
- POST /admin/force-conflict                  demo toggle: next hold returns 409
All writes happen under one process-wide lock inside a DB transaction.
"""
import os
import threading
import time
import uuid
from datetime import date as date_cls, datetime, timedelta
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

import db
import directory

router = APIRouter(prefix="/clinic/v1", tags=["Clinic Booking API"])
_lock = threading.RLock()
_force_conflict = {"next": False}


def hold_ttl() -> int:
    return int(os.getenv("HOLD_TTL_S", "120"))


class HoldRequest(BaseModel):
    doctor_id: str
    date: str
    time: str
    patient_id: str = ""


class BookingRequest(BaseModel):
    hold_id: str
    idempotency_key: str
    patient_id: str = ""


def _all_times(doc: dict, day: date_cls) -> List[str]:
    sch = doc["schedule"]
    if day.weekday() not in sch["days"]:
        return []
    cur = datetime.combine(day, datetime.strptime(sch["start"], "%H:%M").time())
    end = datetime.combine(day, datetime.strptime(sch["end"], "%H:%M").time())
    out = []
    while cur < end:
        out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=sch["slot_minutes"])
    return out


def _parse_date(d: str) -> date_cls:
    try:
        return date_cls.fromisoformat(d)
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD")


def _sweep(s, now: float) -> None:
    for lock in s.exec(select(db.SlotLock).where(db.SlotLock.state == "held", db.SlotLock.expires_at < now)).all():
        h = s.get(db.Hold, lock.hold_id)
        if h and h.status == "active":
            h.status = "expired"
            s.add(h)
        s.delete(lock)
    s.commit()


def open_slots(doctor_id: str, date: str) -> List[str]:
    doc = directory.get_doctor(doctor_id)
    if not doc:
        raise HTTPException(404, "unknown doctor")
    day = _parse_date(date)
    now = time.time()
    with _lock, db.session() as s:
        _sweep(s, now)
        taken = {l.time for l in s.exec(select(db.SlotLock).where(
            db.SlotLock.doctor_id == doctor_id, db.SlotLock.date == date)).all()}
    times = [t for t in _all_times(doc, day) if t not in taken]
    if day == datetime.now().date():  # drop past slots today
        hhmm = datetime.now().strftime("%H:%M")
        times = [t for t in times if t > hhmm]
    return times


@router.get("/slots")
def get_slots(doctor_id: str = Query(...), date: str = Query(...)):
    return {"doctor_id": doctor_id, "date": date, "slots": open_slots(doctor_id, date)}


@router.post("/holds", status_code=201)
def create_hold(req: HoldRequest):
    doc = directory.get_doctor(req.doctor_id)
    if not doc:
        raise HTTPException(404, "unknown doctor")
    if req.time not in _all_times(doc, _parse_date(req.date)):
        raise HTTPException(422, "not a valid slot for this doctor/date")
    now = time.time()
    with _lock, db.session() as s:
        _sweep(s, now)
        if _force_conflict["next"]:
            _force_conflict["next"] = False
            # simulate "someone else just took it"
            if s.get(db.SlotLock, (req.doctor_id, req.date, req.time)) is None:
                s.add(db.SlotLock(doctor_id=req.doctor_id, date=req.date, time=req.time,
                                  state="booked", hold_id="other-patient"))
                s.commit()
            raise HTTPException(409, "slot just taken")
        if s.get(db.SlotLock, (req.doctor_id, req.date, req.time)) is not None:
            raise HTTPException(409, "slot taken")
        hold = db.Hold(id=f"hld_{uuid.uuid4().hex[:10]}", doctor_id=req.doctor_id, date=req.date,
                       time=req.time, patient_id=req.patient_id, expires_at=now + hold_ttl())
        s.add(hold)
        s.add(db.SlotLock(doctor_id=req.doctor_id, date=req.date, time=req.time,
                          state="held", hold_id=hold.id, expires_at=hold.expires_at))
        s.commit()
        return {"hold_id": hold.id, "expires_at": hold.expires_at, "ttl_s": hold_ttl(),
                "doctor_id": hold.doctor_id, "date": hold.date, "time": hold.time}


def _booking_json(b: db.Booking) -> dict:
    return {"booking_id": b.id, "hold_id": b.hold_id, "doctor_id": b.doctor_id, "date": b.date,
            "time": b.time, "patient_id": b.patient_id, "status": b.status}


@router.post("/bookings", status_code=201)
def create_booking(req: BookingRequest):
    now = time.time()
    with _lock, db.session() as s:
        existing = s.exec(select(db.Booking).where(db.Booking.idempotency_key == req.idempotency_key)).first()
        if existing:  # idempotent replay -> original booking
            return _booking_json(existing)
        _sweep(s, now)
        hold = s.get(db.Hold, req.hold_id)
        if hold is None:
            raise HTTPException(404, "unknown hold")
        if hold.status != "active" or hold.expires_at < now:
            raise HTTPException(410, "hold expired")
        booking = db.Booking(id=f"BK{uuid.uuid4().hex[:8].upper()}", hold_id=hold.id, doctor_id=hold.doctor_id,
                             date=hold.date, time=hold.time, patient_id=req.patient_id or hold.patient_id,
                             idempotency_key=req.idempotency_key)
        hold.status = "confirmed"
        lock = s.get(db.SlotLock, (hold.doctor_id, hold.date, hold.time))
        if lock:
            lock.state = "booked"
            lock.expires_at = 0
            s.add(lock)
        s.add(hold)
        s.add(booking)
        s.commit()
        return _booking_json(booking)


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    with db.session() as s:
        b = s.get(db.Booking, booking_id)
        if not b:
            raise HTTPException(404, "unknown booking")
        return _booking_json(b)


@router.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: str):
    with _lock, db.session() as s:
        b = s.get(db.Booking, booking_id)
        if not b:
            raise HTTPException(404, "unknown booking")
        b.status = "cancelled"
        lock = s.get(db.SlotLock, (b.doctor_id, b.date, b.time))
        if lock:
            s.delete(lock)
        s.add(b)
        s.commit()
        return _booking_json(b)


@router.delete("/holds/{hold_id}")
def release_hold(hold_id: str):
    with _lock, db.session() as s:
        h = s.get(db.Hold, hold_id)
        if not h:
            raise HTTPException(404, "unknown hold")
        if h.status == "active":
            h.status = "released"
            lock = s.get(db.SlotLock, (h.doctor_id, h.date, h.time))
            if lock and lock.hold_id == h.id:
                s.delete(lock)
            s.add(h)
            s.commit()
        return {"hold_id": h.id, "status": h.status}


@router.post("/admin/force-conflict")
def force_conflict(on: bool = True):
    _force_conflict["next"] = on
    return {"force_conflict_next": on}
