# -*- coding: utf-8 -*-
"""
ArogyaVaani backend (FastAPI, :8000).

Web contract (Next rewrites /api/* -> here):  /get_config, /startAgent, /stopAgent, /session/*, /call/accept,
/inbox, /console/*, /demo/*, /healthz, /ws/events/{session_id}. Also serves /llm (Agora's custom LLM endpoint),
/clinic/v1 (mock booking API) and /static (voice notes, .ics).
"""
import asyncio
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from dotenv import load_dotenv

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_base_dir, ".env.local"), override=True)
load_dotenv(os.path.join(_base_dir, ".env"), override=True)

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlmodel import select  # noqa: E402
from agora_agent.agentkit.token import generate_convo_ai_token  # noqa: E402

import clinic_api  # noqa: E402
import db  # noqa: E402
import directory  # noqa: E402
import i18n  # noqa: E402
import notify  # noqa: E402
import scheduler  # noqa: E402
from agent_session import manager  # noqa: E402
from events import hub  # noqa: E402
from llm import TURN_LATENCY_MS, app as llm_app, p50  # noqa: E402
from tools import handlers  # noqa: E402

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.engine()
    handlers.HOOKS["request_swap"] = _swap_safely
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="ArogyaVaani API", version="2.0.0",
              description="Voice-first multilingual healthcare agent on Agora ConvoAI + Murf Falcon", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
router = APIRouter()


async def _swap_safely(session_id: str, lang: str) -> None:
    try:
        await manager.hot_swap(session_id, lang)
    except Exception as e:
        logger.exception("hot swap failed")
        hub.publish(session_id, {"type": "error", "text": f"language swap failed: {e}"})


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=f"Internal error: {exc}")


def console_auth(x_console_password: Optional[str] = Header(None)) -> None:
    expected = os.getenv("CONSOLE_PASSWORD")
    if expected and x_console_password != expected:
        raise HTTPException(status_code=401, detail="console password required")


def demo_enabled() -> bool:
    return os.getenv("DEMO_MODE", "1") == "1"


# ------------------------------------------------------------------ connection config & session start
class StartRequest(BaseModel):
    channelName: str
    rtcUid: int
    userUid: int
    sessionId: Optional[str] = None
    patientId: Optional[str] = None
    lang: Optional[str] = None
    elderMode: bool = False
    parameters: Optional[Dict[str, Any]] = None


class StopRequest(BaseModel):
    agentId: Optional[str] = None
    sessionId: Optional[str] = None


class LangRequest(BaseModel):
    lang: str


class SpeakRequest(BaseModel):
    text: str
    priority: str = "INTERRUPT"


@router.get("/get_config")
async def get_config(channel: Optional[str] = Query(default=None), uid: Optional[int] = Query(default=None),
                     patient: Optional[str] = Query(default=None)):
    try:
        app_id, cert = os.getenv("AGORA_APP_ID"), os.getenv("AGORA_APP_CERTIFICATE")
        if not app_id or not cert:
            raise HTTPException(500, "Service not configured: AGORA_APP_ID / AGORA_APP_CERTIFICATE missing")
        user_uid = random.randint(1000, 9999999) if uid is None or uid <= 0 else uid
        agent_uid = str(random.randint(10000000, 99999999))
        session_id = f"s{int(time.time())}{random.randint(100, 999)}"
        channel_name = channel or f"arogya-{session_id}"
        token = generate_convo_ai_token(app_id=app_id, app_certificate=cert, channel_name=channel_name,
                                        uid=user_uid, token_expire=3600)
        pid = patient or f"guest-{session_id}"
        p = db.get_patient(pid)
        return {"code": 0, "msg": "success", "data": {
            "app_id": app_id, "token": token, "uid": str(user_uid), "channel_name": channel_name,
            "agent_uid": agent_uid, "session_id": session_id, "patient_id": pid,
            "lang": p.preferred_lang if p and p.name else "hi-IN", "patient_name": p.name if p else "",
            "elder_mode": bool(p.elder_mode) if p else False}}
    except Exception as e:
        raise _http_error(e)


async def _start(req: StartRequest, greeting: Optional[str] = None, note: str = "", stage: str = "BEFORE",
                 summary: str = "") -> dict:
    sid = req.sessionId or f"s{int(time.time())}{random.randint(100, 999)}"
    pid = req.patientId or f"guest-{sid}"
    p = db.get_patient(pid)
    lang = i18n.normalize_lang(req.lang or (p.preferred_lang if p else "hi-IN"))
    elder = req.elderMode or bool(p and p.elder_mode)
    if p and p.name and greeting is None:
        greeting = i18n.format_template(i18n.GREETING_NAMED, lang, name=p.name)
    db.update_call_session(sid, patient_id=pid, lang=lang, stage=stage, note=note, escalated=False, summary=summary)
    codec = (req.parameters or {}).get("output_audio_codec")
    return await manager.start(sid, req.channelName, req.rtcUid, req.userUid, lang, pid, elder, greeting, codec)


@router.post("/startAgent")
@router.post("/session/start")
async def start_agent(req: StartRequest):
    try:
        data = await _start(req)
        return {"code": 0, "msg": "success", "data": data}
    except Exception as e:
        logger.exception("startAgent failed")
        raise _http_error(e)


@router.post("/stopAgent")
async def stop_agent(req: StopRequest):
    try:
        sid = req.sessionId or next((k for k, v in manager.live.items() if v["agent_id"] == req.agentId), None)
        if sid:
            await manager.stop(sid)
        elif req.agentId:
            await manager.client.stop_agent(req.agentId)
        return {"code": 0, "msg": "success"}
    except Exception as e:
        raise _http_error(e)


@router.post("/session/{session_id}/stop")
async def session_stop(session_id: str):
    try:
        await manager.stop(session_id)
        return {"code": 0, "msg": "success"}
    except Exception as e:
        raise _http_error(e)


@router.post("/session/{session_id}/language")
async def session_language(session_id: str, req: LangRequest):
    try:
        return {"code": 0, "msg": "success", "data": await manager.hot_swap(session_id, req.lang)}
    except Exception as e:
        raise _http_error(e)


@router.post("/session/{session_id}/speak", dependencies=[Depends(console_auth)])
async def session_speak(session_id: str, req: SpeakRequest):
    """Nurse takeover: the agent speaks the given text (Agora /speak, <= 512 bytes)."""
    try:
        res = await manager.speak(session_id, req.text, req.priority)
        hub.publish(session_id, {"type": "nurse_speak", "text": res["spoken"]})
        db.add_transcript(session_id, "nurse", res["spoken"], "")
        return {"code": 0, "msg": "success", "data": res}
    except Exception as e:
        raise _http_error(e)


@router.post("/session/{session_id}/elder")
async def session_elder(session_id: str, on: bool = True):
    """Elder mode lowers the Falcon rate by 10. TTS can't change on a live agent, so restart it (same channel, memory kept)."""
    st = manager.live.get(session_id)
    pid = st["patient_id"] if st else db.get_call_session(session_id).patient_id
    if pid:
        db.upsert_patient(pid, elder_mode=on)
    restarted = False
    if st:
        st["elder"] = on
        try:
            await manager.hot_swap(session_id, st["lang"], force=True)
            restarted = True
        except Exception as e:
            raise _http_error(e)
    return {"code": 0, "elder_mode": on, "restarted": restarted}


# ------------------------------------------------------------------ After: proactive call
class AcceptCall(BaseModel):
    followupId: int
    channelName: str
    rtcUid: int
    userUid: int
    sessionId: Optional[str] = None


@router.post("/call/accept")
async def call_accept(req: AcceptCall):
    """Patient picked up the in-app 'incoming call': start an agent that speaks first (reminder or feedback)."""
    try:
        with db.session() as s:
            f = s.get(db.Followup, req.followupId)
            bk = s.get(db.Booking, f.booking_id) if f else None
        if f is None or bk is None:
            raise HTTPException(404, "unknown followup")
        info = scheduler.call_payload(f)
        lang = i18n.normalize_lang(info["lang"])
        name = info["patient_name"] or ""
        when = i18n.when_phrase(info["date"], info["time"], lang)
        doc = directory.get_doctor(bk.doctor_id)
        if f.kind == "reminder":
            greeting = i18n.format_template(i18n.REMINDER_GREETING, lang, name=name, doctor=info["doctor"], when=when,
                                            prep=notify.prep_tip(doc, lang))
            note = (f"FOLLOW-UP CALL (reminder). You called the patient. Booking {f.booking_id} with {info['doctor']} on "
                    f"{info['date']} {info['time']}. Answer questions about preparation using search_knowledge. Then end warmly.")
        else:
            greeting = i18n.format_template(i18n.FEEDBACK_GREETING, lang, name=name, doctor=info["doctor"])
            note = (f"FOLLOW-UP CALL (feedback). Booking {f.booking_id}. Collect a 1-5 rating from speech ('paanch'=5), call "
                    f"record_feedback, then offer a follow-up appointment with the same doctor using the booking tools.")
        sreq = StartRequest(channelName=req.channelName, rtcUid=req.rtcUid, userUid=req.userUid, sessionId=req.sessionId,
                            patientId=f.patient_id, lang=lang)
        summary = f"{f.booking_id}|{doc['id']}|{info['date']}|{info['time']}"
        data = await _start(sreq, greeting=greeting, note=note, stage="AFTER", summary=summary)
        scheduler.mark_done(f.id)
        return {"code": 0, "msg": "success", "data": {**data, "greeting": greeting}}
    except Exception as e:
        logger.exception("call/accept failed")
        raise _http_error(e)


# ------------------------------------------------------------------ patient data
@router.post("/session/{session_id}/transcript")
async def add_transcript(session_id: str, body: Dict[str, str]):
    """Optional: the web client mirrors RTM transcript lines here so the nurse console has them."""
    db.add_transcript(session_id, body.get("role", "user"), body.get("text", ""), body.get("lang", ""))
    return {"ok": True}


@router.get("/inbox/{patient_id}")
async def inbox(patient_id: str):
    with db.session() as s:
        rows = s.exec(select(db.InboxMessage).where(db.InboxMessage.patient_id == patient_id)
                      .order_by(db.InboxMessage.id.desc()).limit(30)).all()
    return {"messages": [r.model_dump() for r in rows]}


@router.get("/patients/{patient_id}/bookings")
async def patient_bookings(patient_id: str):
    with db.session() as s:
        rows = s.exec(select(db.Booking).where(db.Booking.patient_id == patient_id, db.Booking.status == "confirmed")
                      .order_by(db.Booking.created.desc())).all()
    return {"bookings": [{**b.model_dump(), "doctor": (directory.get_doctor(b.doctor_id) or {}).get("name", "")} for b in rows]}


@router.get("/events/{session_id}")
async def recent_events(session_id: str):
    return {"events": hub.recent(session_id)}


@router.get("/metrics")
async def metrics():
    return {"turns": len(TURN_LATENCY_MS), "p50_ms": round(p50(TURN_LATENCY_MS) or 0)}


# ------------------------------------------------------------------ nurse console
@router.get("/console/sessions", dependencies=[Depends(console_auth)])
async def console_sessions():
    with db.session() as s:
        sessions = s.exec(select(db.CallSession).order_by(db.CallSession.updated.desc()).limit(30)).all()
        bookings = s.exec(select(db.Booking).order_by(db.Booking.created.desc()).limit(20)).all()
        feedback = s.exec(select(db.Feedback).order_by(db.Feedback.id.desc()).limit(20)).all()
    out = []
    for c in sessions:
        p = db.get_patient(c.patient_id)
        out.append({**c.model_dump(), "patient_name": p.name if p else "", "live": c.id in manager.live,
                    "transcript": [t.model_dump() for t in db.recent_transcript(c.id, 5)]})
    return {"sessions": out,
            "bookings": [{**b.model_dump(), "doctor": (directory.get_doctor(b.doctor_id) or {}).get("name", "")} for b in bookings],
            "feedback": [f.model_dump() for f in feedback]}


@router.post("/console/{session_id}/resolve", dependencies=[Depends(console_auth)])
async def console_resolve(session_id: str):
    db.update_call_session(session_id, escalated=False, stage="DURING")
    hub.publish(session_id, {"type": "escalation_resolved"})
    return {"ok": True}


# ------------------------------------------------------------------ demo controls (?demo=1 in UI)
def _demo_guard() -> None:
    if not demo_enabled():
        raise HTTPException(404, "demo controls disabled")


@router.post("/demo/force-conflict", dependencies=[Depends(_demo_guard)])
async def demo_force_conflict(on: bool = True):
    clinic_api._force_conflict["next"] = on
    return {"force_conflict_next": on}


@router.post("/demo/fast-forward/{booking_id}", dependencies=[Depends(_demo_guard)])
@router.post("/demo/fast-forward", dependencies=[Depends(_demo_guard)])
async def demo_fast_forward(booking_id: Optional[str] = None):
    if booking_id is None:
        with db.session() as s:
            b = s.exec(select(db.Booking).where(db.Booking.status == "confirmed").order_by(db.Booking.created.desc())).first()
        booking_id = b.id if b else None
    if not booking_id:
        raise HTTPException(404, "no booking to fast-forward")
    payload = await scheduler.fast_forward(booking_id)
    if payload is None:
        raise HTTPException(404, "no scheduled follow-up left for this booking")
    return {"fired": payload}


def seed_demo() -> dict:
    db.upsert_patient("lakshmi", name="Lakshmi", age=62, area="Jayanagar", languages="kn,hi,en", preferred_lang="hi-IN",
                      phone=os.getenv("DEMO_PATIENT_PHONE", ""), caregiver_name="Ravi",
                      caregiver_phone=os.getenv("DEMO_CAREGIVER_PHONE", ""), elder_mode=False)
    return {"patient_id": "lakshmi"}


@router.post("/demo/reset", dependencies=[Depends(_demo_guard)])
async def demo_reset():
    db.reset_demo_tables()
    clinic_api._force_conflict["next"] = False
    return {"ok": True, **seed_demo()}


@router.post("/demo/seed", dependencies=[Depends(_demo_guard)])
async def demo_seed():
    return {"ok": True, **seed_demo()}


# ------------------------------------------------------------------ health
@router.get("/healthz")
async def healthz():
    import llm_client
    checks: Dict[str, Any] = {}
    try:
        with db.session() as s:
            s.exec(select(db.Patient).limit(1)).all()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {e}"
    checks["llm_configured"] = llm_client.configured()
    checks["murf_key"] = bool(os.getenv("MURF_API_KEY")) and bool(os.getenv("MURF_VOICE_ID"))
    checks["sarvam_key"] = bool(os.getenv("SARVAM_API_KEY"))
    checks["agora_creds"] = bool(os.getenv("AGORA_APP_ID") and os.getenv("AGORA_APP_CERTIFICATE"))
    checks["custom_llm_url_public"] = bool(os.getenv("CUSTOM_LLM_URL")) and "localhost" not in os.getenv("CUSTOM_LLM_URL", "")
    if os.getenv("HEALTHZ_DEEP") == "1" and checks["murf_key"]:
        from http_util import request
        try:
            r = await request("murf_health", "GET", f"{notify.murf_http_base()}/v1/speech/voices",
                              params={"model": "FALCON"}, headers={"api-key": os.getenv("MURF_API_KEY", "")})
            checks["murf_api"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
        except Exception as e:
            checks["murf_api"] = f"fail: {type(e).__name__}"
    ok = checks["db"] == "ok" and checks["agora_creds"]
    return {"status": "ok" if ok else "degraded", "checks": checks, "p50_ms": round(p50(TURN_LATENCY_MS) or 0)}


# ------------------------------------------------------------------ websocket events
@app.websocket("/ws/events/{session_id}")
async def ws_events(ws: WebSocket, session_id: str):
    await ws.accept()
    q = hub.subscribe(session_id)
    try:
        for ev in hub.recent(session_id)[-50:]:
            await ws.send_json(ev)
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=20)
                await ws.send_json(ev)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(session_id, q)


app.include_router(router)
app.include_router(clinic_api.router)
app.mount("/llm", llm_app)
os.makedirs(notify.static_dir(), exist_ok=True)
app.mount("/static", StaticFiles(directory=notify.static_dir()), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
