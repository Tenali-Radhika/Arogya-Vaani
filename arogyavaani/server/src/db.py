"""SQLModel storage: patients, sessions, clinic booking tables, inbox, feedback, follow-ups."""
import os
import time
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_engine = None


def db_path() -> str:
    return os.getenv("AROGYA_DB_PATH") or os.path.join(_BASE, "arogya.db")


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{db_path()}", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(_engine)
    return _engine


def reset_engine():
    """Dispose the cached engine (tests / demo reset pick up a new AROGYA_DB_PATH)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def session() -> Session:
    return Session(engine(), expire_on_commit=False)


class Patient(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = ""
    age: Optional[int] = None
    area: str = ""
    languages: str = "hi,en"          # comma separated
    preferred_lang: str = "hi-IN"
    phone: str = ""
    caregiver_phone: str = ""
    caregiver_name: str = ""
    elder_mode: bool = False
    last_summary: str = ""


class CallSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    patient_id: str = "anon"
    lang: str = "hi-IN"
    stage: str = "BEFORE"
    agent_id: str = ""
    channel: str = ""
    escalated: bool = False
    escalation_reason: str = ""
    summary: str = ""
    note: str = ""  # extra prompt context (e.g. follow-up call instructions)
    created: float = Field(default_factory=time.time)
    updated: float = Field(default_factory=time.time)


class TranscriptLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    role: str
    text: str
    lang: str = ""
    ts: float = Field(default_factory=time.time)


class SlotLock(SQLModel, table=True):
    """One row per (doctor, date, time). state: held | booked. Held rows expire."""
    doctor_id: str = Field(primary_key=True)
    date: str = Field(primary_key=True)
    time: str = Field(primary_key=True)
    state: str = "held"
    hold_id: str = ""
    expires_at: float = 0.0


class Hold(SQLModel, table=True):
    id: str = Field(primary_key=True)
    doctor_id: str
    date: str
    time: str
    patient_id: str = ""
    expires_at: float = 0.0
    status: str = "active"  # active | confirmed | released | expired


class Booking(SQLModel, table=True):
    id: str = Field(primary_key=True)
    hold_id: str
    doctor_id: str
    date: str
    time: str
    patient_id: str = ""
    idempotency_key: str = Field(index=True, unique=True)
    status: str = "confirmed"  # confirmed | cancelled
    created: float = Field(default_factory=time.time)


class InboxMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(index=True)
    recipient: str = "patient"  # patient | caregiver
    channel: str = "inbox"
    text: str = ""
    media_url: str = ""
    ics_url: str = ""
    delivered: bool = True
    created: float = Field(default_factory=time.time)


class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    booking_id: str
    patient_id: str = ""
    rating: int
    comment: str = ""
    created: float = Field(default_factory=time.time)


class Followup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    booking_id: str = Field(index=True)
    patient_id: str = ""
    kind: str  # reminder | feedback
    run_at: float
    status: str = "scheduled"  # scheduled | fired | done


def get_patient(pid: str) -> Optional[Patient]:
    with session() as s:
        return s.get(Patient, pid)


def upsert_patient(pid: str, **fields) -> Patient:
    with session() as s:
        p = s.get(Patient, pid) or Patient(id=pid)
        for k, v in fields.items():
            if v is not None and hasattr(p, k):
                setattr(p, k, v)
        s.add(p)
        s.commit()
        return p


def get_call_session(sid: str) -> CallSession:
    with session() as s:
        c = s.get(CallSession, sid)
        if c is None:
            c = CallSession(id=sid)
            s.add(c)
            s.commit()
        return c


def update_call_session(sid: str, **fields) -> CallSession:
    with session() as s:
        c = s.get(CallSession, sid) or CallSession(id=sid)
        for k, v in fields.items():
            setattr(c, k, v)
        c.updated = time.time()
        s.add(c)
        s.commit()
        return c


def add_transcript(sid: str, role: str, text: str, lang: str = "") -> None:
    with session() as s:
        s.add(TranscriptLine(session_id=sid, role=role, text=text, lang=lang))
        s.commit()


def recent_transcript(sid: str, n: int = 5):
    with session() as s:
        rows = s.exec(select(TranscriptLine).where(TranscriptLine.session_id == sid)
                      .order_by(TranscriptLine.id.desc()).limit(n)).all()
    return list(reversed(rows))


def reset_demo_tables() -> None:
    with session() as s:
        for model in (SlotLock, Hold, Booking, InboxMessage, Feedback, Followup, TranscriptLine, CallSession):
            for row in s.exec(select(model)).all():
                s.delete(row)
        s.commit()
