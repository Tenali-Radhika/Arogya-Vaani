"""APScheduler: reminder call (T-12h) and feedback call (T+2h). Firing pushes an `incoming_call` UI event."""
import logging
import time
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select

import db
import directory
from events import hub

logger = logging.getLogger("arogya.scheduler")
IST = ZoneInfo("Asia/Kolkata")
REMINDER_BEFORE_S = 12 * 3600
FEEDBACK_AFTER_S = 2 * 3600

sched = AsyncIOScheduler(timezone=IST)


def start() -> None:
    if not sched.running:
        sched.start()
    restore_jobs()


def shutdown() -> None:
    if sched.running:
        sched.shutdown(wait=False)


def slot_epoch(date: str, hhmm: str) -> float:
    return datetime.fromisoformat(f"{date}T{hhmm}:00").replace(tzinfo=IST).timestamp()


def _add_job(fid: int, run_at: float) -> None:
    sched.add_job(fire, "date", run_date=datetime.fromtimestamp(run_at, IST), args=[fid],
                  id=f"followup-{fid}", replace_existing=True, misfire_grace_time=3600)


def schedule_for_booking(booking: dict, patient_id: str) -> List[dict]:
    slot = slot_epoch(booking["date"], booking["time"])
    now = time.time()
    plan = [("reminder", slot - REMINDER_BEFORE_S), ("feedback", slot + FEEDBACK_AFTER_S)]
    out = []
    with db.session() as s:
        for kind, run_at in plan:
            if kind == "reminder" and run_at < now < slot:
                run_at = now + 30  # booked inside the 12h window: remind shortly
            existing = s.exec(select(db.Followup).where(db.Followup.booking_id == booking["booking_id"],
                                                        db.Followup.kind == kind)).first()
            if existing:
                f = existing
            else:
                f = db.Followup(booking_id=booking["booking_id"], patient_id=patient_id, kind=kind, run_at=run_at)
                s.add(f)
                s.commit()
            _add_job(f.id, f.run_at)
            out.append({"id": f.id, "kind": kind, "run_at": datetime.fromtimestamp(f.run_at, IST).isoformat()})
    return out


def restore_jobs() -> None:
    with db.session() as s:
        for f in s.exec(select(db.Followup).where(db.Followup.status == "scheduled")).all():
            _add_job(f.id, max(f.run_at, time.time() + 5))


def call_payload(f: db.Followup) -> dict:
    with db.session() as s:
        b = s.get(db.Booking, f.booking_id)
    doc = directory.get_doctor(b.doctor_id) if b else None
    p = db.get_patient(f.patient_id)
    return {"followup_id": f.id, "kind": f.kind, "booking_id": f.booking_id, "patient_id": f.patient_id,
            "patient_name": p.name if p else "", "lang": p.preferred_lang if p else "hi-IN",
            "doctor": doc["name"] if doc else "", "clinic": doc["clinic"] if doc else "",
            "date": b.date if b else "", "time": b.time if b else ""}


async def fire(followup_id: int) -> Optional[dict]:
    with db.session() as s:
        f = s.get(db.Followup, followup_id)
        if f is None or f.status != "scheduled":
            return None
        f.status = "fired"
        s.add(f)
        s.commit()
    payload = call_payload(f)
    logger.info("firing followup %s", payload)
    hub.publish(f"patient:{f.patient_id}", {"type": "incoming_call", **payload})
    return payload


async def fast_forward(booking_id: str) -> Optional[dict]:
    """Demo: fire the next not-yet-fired followup for this booking right now (reminder, then feedback)."""
    with db.session() as s:
        f = s.exec(select(db.Followup).where(db.Followup.booking_id == booking_id, db.Followup.status == "scheduled")
                   .order_by(db.Followup.run_at)).first()
    if f is None:
        return None
    try:
        sched.remove_job(f"followup-{f.id}")
    except Exception:
        pass
    return await fire(f.id)


def mark_done(followup_id: int) -> None:
    with db.session() as s:
        f = s.get(db.Followup, followup_id)
        if f:
            f.status = "done"
            s.add(f)
            s.commit()
