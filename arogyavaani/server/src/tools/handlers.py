"""Tool implementations. Every booking tool talks to the Clinic Booking API over HTTP (httpx)."""
import hashlib
import os
from datetime import date as date_cls, timedelta
from typing import List, Optional

import db
import directory
import i18n
import kb
import notify
import triage as triage_mod
from events import hub
from http_util import request
from tools.registry import ToolContext, tool

# Set by server wiring: async callables. Kept as hooks so tools stay free of the agora SDK.
HOOKS = {"schedule_followup": None, "request_swap": None}
PENDING_SWAPS: dict = {}  # session_id -> lang (executed after the current reply finishes streaming)


def clinic_base() -> str:
    return os.getenv("CLINIC_API_URL") or f"http://127.0.0.1:{os.getenv('PORT', '8000')}/clinic/v1"


async def _clinic(name: str, method: str, path: str, **kw):
    return await request(f"clinic.{name}", method, clinic_base() + path, use_override=True, **kw)


def _set_stage(ctx: ToolContext, stage: str) -> None:
    db.update_call_session(ctx.session_id, stage=stage)
    hub.publish(ctx.session_id, {"type": "stage", "stage": stage})


def _doc_brief(d: dict) -> dict:
    return {"id": d["id"], "name": d["name"], "specialty": d["specialty"], "clinic": d["clinic"],
            "area": d["area"], "languages": d["languages_spoken"], "fee_inr": d["fee_inr"],
            "pmjay": d["pmjay_empanelled"], "rating": d["rating"]}


# --------------------------------------------------------------------------- profile
@tool("get_patient_profile", "Load the saved profile and recent bookings for the current patient (call at the start).",
      summary=lambda r: f"profile: {r['profile']['name']}" if r.get("exists") else "new patient")
async def get_patient_profile(ctx: ToolContext) -> dict:
    p = db.get_patient(ctx.patient_id)
    if not p or not p.name:
        return {"exists": False}
    with db.session() as s:
        from sqlmodel import select
        bks = s.exec(select(db.Booking).where(db.Booking.patient_id == p.id, db.Booking.status == "confirmed")
                     .order_by(db.Booking.created.desc()).limit(3)).all()
    return {"exists": True, "profile": {"name": p.name, "age": p.age, "area": p.area, "languages": p.languages,
                                        "preferred_lang": p.preferred_lang, "caregiver_name": p.caregiver_name,
                                        "has_caregiver": bool(p.caregiver_phone)},
            "bookings": [{"booking_id": b.id, "doctor_id": b.doctor_id, "date": b.date, "time": b.time} for b in bks]}


@tool("save_patient_profile", "Save or update patient details collected by voice.",
      {"type": "object", "properties": {
          "name": {"type": "string"}, "age": {"type": "integer"}, "area": {"type": "string", "description": "Bengaluru locality"},
          "languages": {"type": "array", "items": {"type": "string", "enum": ["kn", "hi", "en", "ta", "te", "ml"]}},
          "caregiver_phone": {"type": "string", "description": "E.164 phone"}, "caregiver_name": {"type": "string"},
          "phone": {"type": "string"}}},
      summary=lambda r: "profile saved")
async def save_patient_profile(ctx: ToolContext, name=None, age=None, area=None, languages=None,
                               caregiver_phone=None, caregiver_name=None, phone=None) -> dict:
    fields = dict(name=name, age=age, area=area, caregiver_phone=caregiver_phone,
                  caregiver_name=caregiver_name, phone=phone)
    if languages:
        fields["languages"] = ",".join(languages)
    db.upsert_patient(ctx.patient_id, **fields)
    return {"ok": True, "saved": [k for k, v in fields.items() if v is not None]}


# --------------------------------------------------------------------------- triage & search
def _triage_summary(r: dict) -> str:
    return f"RED FLAG: {r['category']}" if r.get("red_flag") else f"{r['specialty']} ({r['urgency']})"


@tool("triage_symptoms",
      "Map the patient's symptoms to a specialty and urgency and check red flags. Never diagnoses. Call before searching doctors.",
      {"type": "object", "properties": {
          "symptoms": {"type": "string", "description": "Patient's words verbatim (any language)"},
          "specialty_hint": {"type": "string", "description": "Your best guess of the specialty if unsure"}},
       "required": ["symptoms"]},
      summary=_triage_summary)
async def triage_symptoms(ctx: ToolContext, symptoms: str, specialty_hint: Optional[str] = None) -> dict:
    r = triage_mod.triage(symptoms, specialty_hint)
    if r["red_flag"]:
        await escalate(ctx, reason=r["category"], auto=True)
    else:
        _set_stage(ctx, "DURING")
    return r


@tool("geocode_area", "Convert a Bengaluru locality name into coordinates.",
      {"type": "object", "properties": {"area": {"type": "string"}}, "required": ["area"]},
      summary=lambda r: r.get("area", "unknown area"))
async def geocode_area(ctx: ToolContext, area: str) -> dict:
    g = directory.geocode_area(area)
    return g or {"ok": False, "error": "unknown area"}


def rank_doctors(specialty: str, area: Optional[str], langs: List[str], max_fee: Optional[int] = None,
                 pmjay_only: bool = False, top: int = 3) -> List[dict]:
    g = directory.geocode_area(area) if area else None
    origin = (g["lat"], g["lng"]) if g else None
    out = []
    for d in directory.doctors():
        if specialty and d["specialty"].lower() != specialty.lower():
            continue
        if pmjay_only and not d["pmjay_empanelled"]:
            continue
        if max_fee and d["fee_inr"] > max_fee:
            continue
        matched = [l for l in langs if l in d["languages_spoken"]]
        dist = directory.haversine_km(origin, (d["lat"], d["lng"])) if origin else None
        score = 3.0 * len(matched) + d["rating"] * 0.5 - (dist or 0) * 0.15 - d["fee_inr"] / 1500 + (0.5 if d["pmjay_empanelled"] else 0)
        why = []
        if matched:
            why.append("speaks " + "/".join(matched))
        if dist is not None:
            why.append(f"{dist:.1f} km away")
        why.append(f"Rs {d['fee_inr']}")
        if d["pmjay_empanelled"]:
            why.append("PM-JAY")
        out.append({**_doc_brief(d), "distance_km": round(dist, 1) if dist is not None else None,
                    "language_match": matched, "score": round(score, 2), "why": ", ".join(why)})
    out.sort(key=lambda x: -x["score"])
    return out[:top]


@tool("search_doctors", "Find and rank doctors by specialty, distance, spoken language, fee and PM-JAY. Returns top 3 with reasons.",
      {"type": "object", "properties": {
          "specialty": {"type": "string", "enum": ["general physician", "orthopaedics", "paediatrics", "gynaecology", "cardiology", "dermatology", "ENT", "ophthalmology", "diabetology"]},
          "area": {"type": "string", "description": "Patient's locality; defaults to saved profile area"},
          "languages": {"type": "array", "items": {"type": "string"}, "description": "Doctor languages wanted, e.g. [\"kn\",\"hi\"]"},
          "max_fee": {"type": "integer"}, "pmjay_only": {"type": "boolean"}},
       "required": ["specialty"]},
      summary=lambda r: f"{len(r.get('doctors', []))} doctors: " + ", ".join(d['name'] for d in r.get('doctors', [])))
async def search_doctors(ctx: ToolContext, specialty: str, area: Optional[str] = None, languages: Optional[List[str]] = None,
                         max_fee: Optional[int] = None, pmjay_only: bool = False) -> dict:
    p = db.get_patient(ctx.patient_id)
    area = area or (p.area if p else None)
    langs = languages or ([l for l in (p.languages.split(",") if p else []) if l] or [i18n.LANG_SHORT[ctx.lang]])
    docs = rank_doctors(specialty, area, langs, max_fee, pmjay_only)
    hub.publish(ctx.session_id, {"type": "doctors", "doctors": docs})
    return {"doctors": docs, "area_used": area, "languages_used": langs}


@tool("search_knowledge", "Look up pre-visit preparation, PM-JAY/Ayushman basics and clinic policies.",
      {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
      summary=lambda r: f"{len(r.get('results', []))} facts")
async def search_knowledge(ctx: ToolContext, query: str) -> dict:
    return {"results": kb.retrieve(query, 3)}


# --------------------------------------------------------------------------- booking
@tool("check_availability", "List open appointment slots for a doctor on a date (YYYY-MM-DD). Use dates relative to TODAY in the system prompt.",
      {"type": "object", "properties": {"doctor_id": {"type": "string"}, "date": {"type": "string"}},
       "required": ["doctor_id", "date"]},
      summary=lambda r: f"{len(r.get('slots', []))} slots on {r.get('date')}")
async def check_availability(ctx: ToolContext, doctor_id: str, date: str) -> dict:
    r = await _clinic("slots", "GET", "/slots", params={"doctor_id": doctor_id, "date": date})
    if r.status_code != 200:
        return {"ok": False, "error": r.text[:200]}
    slots = r.json()["slots"]
    return {"doctor_id": doctor_id, "date": date, "slots": slots[:10], "total_open": len(slots)}


async def _alternatives(doctor_id: str, date: str, around: str, n: int = 2) -> List[str]:
    r = await _clinic("slots", "GET", "/slots", params={"doctor_id": doctor_id, "date": date})
    slots = r.json().get("slots", []) if r.status_code == 200 else []
    slots.sort(key=lambda t: abs(int(t[:2]) * 60 + int(t[3:]) - (int(around[:2]) * 60 + int(around[3:]))))
    return sorted(slots[:n])


@tool("hold_slot", "Place a 120-second hold on a slot. Always do this before asking the patient to confirm. Returns hold_id, or conflict with alternatives.",
      {"type": "object", "properties": {"doctor_id": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string", "description": "HH:MM 24h"}},
       "required": ["doctor_id", "date", "time"]},
      summary=lambda r: "CONFLICT: slot taken" if r.get("conflict") else (f"held until +{r.get('ttl_s')}s" if r.get("hold_id") else "hold failed"))
async def hold_slot(ctx: ToolContext, doctor_id: str, date: str, time: str) -> dict:
    red = db.get_call_session(ctx.session_id)
    if red.escalated:
        return {"ok": False, "error": "booking is stopped because an emergency escalation is open"}
    try:
        r = await _clinic("hold", "POST", "/holds", json={"doctor_id": doctor_id, "date": date, "time": time,
                                                          "patient_id": ctx.patient_id})
    except Exception:
        return {"ok": False, "error": "timeout", "callback": True,
                "note": "Booking service is slow. Promise the patient a callback."}
    if r.status_code == 409:
        alts = await _alternatives(doctor_id, date, time)
        return {"ok": False, "conflict": True, "alternatives": alts,
                "note": "That slot was just taken. Offer these two alternatives."}
    if r.status_code != 201:
        return {"ok": False, "error": r.text[:200]}
    _set_stage(ctx, "ACTION")
    j = r.json()
    ctx.extra["hold"] = j
    return {"ok": True, **j}


@tool("confirm_booking", "Confirm a held slot AFTER the patient said yes. Idempotent.",
      {"type": "object", "properties": {"hold_id": {"type": "string"}}, "required": ["hold_id"]},
      summary=lambda r: f"booked {r.get('booking_id')}" if r.get("booking_id") else "booking failed")
async def confirm_booking(ctx: ToolContext, hold_id: str) -> dict:
    key = hashlib.sha1(f"{ctx.session_id}:{hold_id}".encode()).hexdigest()[:20]
    try:
        r = await _clinic("confirm", "POST", "/bookings", json={"hold_id": hold_id, "idempotency_key": key,
                                                                "patient_id": ctx.patient_id})
    except Exception:
        return {"ok": False, "error": "timeout", "callback": True,
                "note": "Could not reach booking service. Tell the patient we will call back to confirm."}
    if r.status_code == 410:
        return {"ok": False, "expired": True, "note": "Hold expired. Place a new hold."}
    if r.status_code not in (200, 201):
        return {"ok": False, "error": r.text[:200]}
    b = r.json()
    doc = directory.get_doctor(b["doctor_id"])
    _set_stage(ctx, "CONFIRM")
    db.update_call_session(ctx.session_id, summary=f"{b['booking_id']}|{b['doctor_id']}|{b['date']}|{b['time']}")
    hub.publish(ctx.session_id, {"type": "appointment", "booking": b, "doctor": _doc_brief(doc) if doc else None})
    return {"ok": True, **b, "doctor_name": doc["name"] if doc else "", "clinic": doc["clinic"] if doc else ""}


@tool("cancel_booking", "Cancel a confirmed booking, or release an unconfirmed hold if the patient changes their mind.",
      {"type": "object", "properties": {"booking_id": {"type": "string"}, "hold_id": {"type": "string"}}},
      summary=lambda r: "cancelled" if r.get("ok") else "cancel failed")
async def cancel_booking(ctx: ToolContext, booking_id: Optional[str] = None, hold_id: Optional[str] = None) -> dict:
    if booking_id:
        r = await _clinic("cancel", "DELETE", f"/bookings/{booking_id}")
    elif hold_id:
        r = await _clinic("release", "DELETE", f"/holds/{hold_id}")
    else:
        return {"ok": False, "error": "booking_id or hold_id required"}
    return {"ok": r.status_code == 200, **(r.json() if r.status_code == 200 else {"error": r.text[:200]})}


# --------------------------------------------------------------------------- confirm & after
async def _booking_details(booking_id: str) -> Optional[dict]:
    r = await _clinic("get_booking", "GET", f"/bookings/{booking_id}")
    return r.json() if r.status_code == 200 else None


async def make_voice_note(booking: dict, doctor: dict, lang: str) -> Optional[str]:
    text = i18n.format_template(i18n.VOICE_NOTE, lang, doctor=doctor["name"],
                                date=i18n.spoken_date(booking["date"], lang),
                                time=i18n.spoken_time(booking["time"], lang), prep=notify.prep_tip(doctor, lang))
    return await notify.generate_voice_note(text, lang, booking["booking_id"])


@tool("generate_voice_note", "Create a short spoken audio summary of a booking (Murf) for patients who cannot read.",
      {"type": "object", "properties": {"booking_id": {"type": "string"}}, "required": ["booking_id"]},
      summary=lambda r: r.get("url") or "voice note unavailable")
async def generate_voice_note(ctx: ToolContext, booking_id: str) -> dict:
    b = await _booking_details(booking_id)
    if not b:
        return {"ok": False, "error": "unknown booking"}
    url = await make_voice_note(b, directory.get_doctor(b["doctor_id"]), ctx.lang)
    return {"ok": url is not None, "url": url, "error": None if url else "MURF_API_KEY / MURF_VOICE_ID not configured"}


@tool("send_confirmation", "Send the booking confirmation (WhatsApp/SMS + in-app inbox) with voice note and calendar invite to the patient and caregiver.",
      {"type": "object", "properties": {"booking_id": {"type": "string"}}, "required": ["booking_id"]},
      summary=lambda r: "sent via " + ", ".join(f"{m['recipient']}:{m['channel']}" for m in r.get("messages", [])) if r.get("ok") else "send failed")
async def send_confirmation(ctx: ToolContext, booking_id: str) -> dict:
    b = await _booking_details(booking_id)
    if not b:
        return {"ok": False, "error": "unknown booking"}
    doc = directory.get_doctor(b["doctor_id"])
    p = db.get_patient(ctx.patient_id)
    lang = ctx.lang
    ics = notify.write_ics(b, doc)
    voice = None
    try:
        voice = await make_voice_note(b, doc, lang)
    except Exception:  # voice note is a bonus: never block the confirmation
        hub.publish(ctx.session_id, {"type": "warning", "text": "voice note failed; sent text only"})
    msgs = [await notify.deliver(ctx.patient_id, "patient", p.phone if p else "",
                                 notify.build_confirmation(b, doc, p.name if p else "", lang), voice or "", ics)]
    if p and (p.caregiver_phone or p.caregiver_name):
        msgs.append(await notify.deliver(ctx.patient_id, "caregiver", p.caregiver_phone,
                                         notify.build_confirmation(b, doc, p.name, lang, caregiver=True), voice or "", ics))
    hub.publish(ctx.session_id, {"type": "inbox", "messages": msgs, "voice_note": voice, "ics": ics})
    return {"ok": True, "messages": msgs, "voice_note": voice, "ics": ics}


@tool("schedule_followup", "Schedule the reminder call (12h before) and the feedback call (2h after) for a booking.",
      {"type": "object", "properties": {"booking_id": {"type": "string"}}, "required": ["booking_id"]},
      summary=lambda r: f"{len(r.get('jobs', []))} calls scheduled")
async def schedule_followup(ctx: ToolContext, booking_id: str) -> dict:
    b = await _booking_details(booking_id)
    if not b:
        return {"ok": False, "error": "unknown booking"}
    import scheduler
    jobs = scheduler.schedule_for_booking(b, ctx.patient_id)
    return {"ok": True, "jobs": jobs}


@tool("record_feedback", "Save the patient's 1-5 rating and optional comment after the visit.",
      {"type": "object", "properties": {"booking_id": {"type": "string"}, "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                                        "comment": {"type": "string"}}, "required": ["booking_id", "rating"]},
      summary=lambda r: f"rating {r.get('rating')}/5 saved")
async def record_feedback(ctx: ToolContext, booking_id: str, rating: int, comment: str = "") -> dict:
    rating = max(1, min(5, int(rating)))
    with db.session() as s:
        s.add(db.Feedback(booking_id=booking_id, patient_id=ctx.patient_id, rating=rating, comment=comment))
        s.commit()
    _set_stage(ctx, "AFTER")
    hub.publish(ctx.session_id, {"type": "feedback", "booking_id": booking_id, "rating": rating, "comment": comment})
    return {"ok": True, "rating": rating}


# --------------------------------------------------------------------------- language & human
@tool("set_language", "Switch the conversation language when the patient asks (e.g. 'Kannada dalli maathadi', 'Hindi mein baat karo').",
      {"type": "object", "properties": {"language": {"type": "string", "enum": ["hi-IN", "kn-IN", "en-IN"]}}, "required": ["language"]},
      summary=lambda r: f"switching to {r.get('language')}")
async def set_language(ctx: ToolContext, language: str) -> dict:
    lang = i18n.normalize_lang(language)
    if lang == ctx.lang:
        return {"ok": True, "language": lang, "note": "already speaking this language"}
    PENDING_SWAPS[ctx.session_id] = lang
    return {"ok": True, "language": lang,
            "note": "Say ONE short sentence in the NEW language that you are switching. The call reconnects in a moment."}


async def escalate(ctx: ToolContext, reason: str, auto: bool = False) -> dict:
    db.update_call_session(ctx.session_id, escalated=True, escalation_reason=reason, stage="ESCALATED")
    hub.publish(ctx.session_id, {"type": "red_flag", "reason": reason, "auto": auto})
    hub.publish(ctx.session_id, {"type": "stage", "stage": "ESCALATED"})
    return {"ok": True, "escalated": True, "reason": reason}


@tool("escalate_to_human", "Hand the call to a human nurse. Use for any emergency or when the patient asks for a person.",
      {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]},
      summary=lambda r: "nurse alerted")
async def escalate_to_human(ctx: ToolContext, reason: str) -> dict:
    return await escalate(ctx, reason)
