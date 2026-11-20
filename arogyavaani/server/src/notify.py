"""Confirmation messages, .ics invites, Murf voice notes, Twilio WhatsApp/SMS with inbox fallback."""
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional

import db
import i18n
from http_util import request

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def static_dir() -> str:
    d = os.getenv("STATIC_DIR") or os.path.join(_BASE, "static")
    os.makedirs(os.path.join(d, "voice"), exist_ok=True)
    os.makedirs(os.path.join(d, "ics"), exist_ok=True)
    return d


def public_url(path: str) -> str:
    base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    return f"{base}{path}"


def murf_http_base() -> str:
    # India endpoint for the HTTP stream API (wss in.api.murf.ai is used for the realtime pipeline).
    return os.getenv("MURF_HTTP_BASE", "https://in.api.murf.ai").rstrip("/")


def murf_voice_id() -> str:
    return os.getenv("MURF_VOICE_ID", "")


def prep_tip(doctor: dict, lang: str) -> str:
    spec = doctor.get("specialty", "")
    tips = {
        "orthopaedics": {"hi-IN": "अपनी पुरानी X-ray और रिपोर्ट साथ लाइए।", "kn-IN": "ದಯವಿಟ್ಟು ಹಳೆಯ X-ray ಮತ್ತು ವರದಿ ತನ್ನಿ.", "en-IN": "Please bring your old X-rays and reports."},
        "diabetology": {"hi-IN": "सुबह खाली पेट आइए, पानी पी सकते हैं।", "kn-IN": "ಬೆಳಿಗ್ಗೆ ಖಾಲಿ ಹೊಟ್ಟೆಯಲ್ಲಿ ಬನ್ನಿ, ನೀರು ಕುಡಿಯಬಹುದು.", "en-IN": "Come fasting in the morning; water is fine."},
    }
    return (tips.get(spec) or i18n.PREP_DEFAULT).get(lang, i18n.PREP_DEFAULT["hi-IN"])


def build_confirmation(booking: dict, doctor: dict, patient_name: str, lang: str, caregiver: bool = False) -> str:
    kw = dict(doctor=doctor["name"], clinic=doctor["clinic"], date=i18n.spoken_date(booking["date"], lang),
              time=i18n.spoken_time(booking["time"], lang), bid=booking["booking_id"],
              prep=prep_tip(doctor, lang), patient=patient_name or "Patient")
    return i18n.format_template(i18n.CAREGIVER_MSG if caregiver else i18n.CONFIRM_MSG, lang, **kw)


def make_ics(booking: dict, doctor: dict) -> str:
    start = datetime.fromisoformat(f"{booking['date']}T{booking['time']}:00")
    end = start + timedelta(minutes=30)
    fmt = "%Y%m%dT%H%M%S"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ArogyaVaani//EN", "BEGIN:VEVENT",
             f"UID:{booking['booking_id']}@arogyavaani", f"DTSTAMP:{datetime.utcnow().strftime(fmt)}Z",
             f"DTSTART;TZID=Asia/Kolkata:{start.strftime(fmt)}", f"DTEND;TZID=Asia/Kolkata:{end.strftime(fmt)}",
             f"SUMMARY:Appointment with {doctor['name']}", f"LOCATION:{doctor['clinic']}",
             f"DESCRIPTION:Booking ID {booking['booking_id']}. Fictional demo booking.",
             "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", "DESCRIPTION:Doctor appointment", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def write_ics(booking: dict, doctor: dict) -> str:
    path = os.path.join(static_dir(), "ics", f"{booking['booking_id']}.ics")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(make_ics(booking, doctor))
    return f"/static/ics/{booking['booking_id']}.ics"


# Words Falcon should say correctly regardless of surrounding script.
PRONUNCIATIONS = {"ArogyaVaani": {"type": "SAY_AS", "pronunciation": "Aarogya Vaani"},
                  "PM-JAY": {"type": "SAY_AS", "pronunciation": "P M J A Y"},
                  "ECG": {"type": "SAY_AS", "pronunciation": "E C G"},
                  "MRI": {"type": "SAY_AS", "pronunciation": "M R I"}}


async def generate_voice_note(text: str, lang: str, booking_id: str) -> Optional[str]:
    """Murf HTTP stream TTS -> static/voice/{booking_id}-{hash}.mp3. Cached by text hash. None if no key."""
    key = os.getenv("MURF_API_KEY")
    if not key or not murf_voice_id():
        return None
    h = hashlib.sha1(f"{lang}|{murf_voice_id()}|{text}".encode()).hexdigest()[:10]
    name = f"{booking_id}-{h}.mp3"
    path = os.path.join(static_dir(), "voice", name)
    if not os.path.exists(path):
        body = {"text": text, "voiceId": murf_voice_id(), "model": os.getenv("MURF_HTTP_MODEL", "falcon-2.1"), "locale": lang,
                "format": "MP3", "sampleRate": 24000, "pronunciationDictionary": PRONUNCIATIONS}
        r = await request("murf_voice_note", "POST", f"{murf_http_base()}/v1/speech/stream",
                          headers={"api-key": key, "Content-Type": "application/json"}, json=body)
        if r.status_code != 200 or not r.content:
            raise RuntimeError(f"Murf TTS failed: {r.status_code} {r.text[:200]}")
        with open(path, "wb") as f:
            f.write(r.content)
    return f"/static/voice/{name}"


async def _twilio_send(to: str, text: str, media_url: str = "") -> Optional[str]:
    sid, tok = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")
    if not (sid and tok and to):
        return None
    wa_from = os.getenv("TWILIO_WHATSAPP_FROM")  # e.g. whatsapp:+14155238886 (sandbox)
    sms_from = os.getenv("TWILIO_SMS_FROM")
    attempts = []
    if wa_from:
        attempts.append(("whatsapp", wa_from, f"whatsapp:{to}"))
    if sms_from:
        attempts.append(("sms", sms_from, to))
    for channel, frm, dest in attempts:
        data = {"From": frm, "To": dest, "Body": text}
        if media_url and channel == "whatsapp" and media_url.startswith("http"):
            data["MediaUrl"] = media_url
        try:
            r = await request("twilio_" + channel, "POST",
                              f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                              data=data, auth=(sid, tok))
            if r.status_code < 300:
                return channel
        except Exception:
            continue
    return None


async def deliver(patient_id: str, recipient: str, phone: str, text: str,
                  media_path: str = "", ics_path: str = "") -> dict:
    """Always writes the in-app inbox; additionally tries Twilio. Twilio failure never raises."""
    media_url = public_url(media_path) if media_path else ""
    channel = await _twilio_send(phone, text, media_url)
    with db.session() as s:
        msg = db.InboxMessage(patient_id=patient_id, recipient=recipient, channel=channel or "inbox", text=text,
                              media_url=media_path, ics_url=ics_path, delivered=bool(channel) or not phone)
        s.add(msg)
        s.commit()
        return {"id": msg.id, "channel": msg.channel, "recipient": recipient, "delivered": msg.delivered}
