"""Per-language strings (hi-IN, kn-IN, en-IN): greetings, fillers, emergency lines, templates, spoken times."""
import random
from datetime import date as date_cls
from typing import Dict

LANGS = ("hi-IN", "kn-IN", "en-IN")
LANG_NAMES = {"hi-IN": "Hindi", "kn-IN": "Kannada", "en-IN": "English"}
LANG_SHORT = {"hi-IN": "hi", "kn-IN": "kn", "en-IN": "en"}


def normalize_lang(x: str) -> str:
    x = (x or "").lower()
    if x.startswith("kn") or "kannada" in x or "ಕನ್ನಡ" in x or "kannad" in x:
        return "kn-IN"
    if x.startswith("hi") or "hindi" in x or "हिंदी" in x or "हिन्दी" in x:
        return "hi-IN"
    if x.startswith("en") or "english" in x or "angrezi" in x:
        return "en-IN"
    return "hi-IN"


GREETING = {
    "hi-IN": "नमस्ते! मैं ArogyaVaani हूँ। बताइए, आज क्या तकलीफ़ है?",
    "kn-IN": "ನಮಸ್ಕಾರ! ನಾನು ArogyaVaani. ಇಂದು ಏನು ತೊಂದರೆ ಇದೆ ಹೇಳಿ?",
    "en-IN": "Hello! I'm ArogyaVaani. Tell me, what is troubling you today?",
}
GREETING_NAMED = {
    "hi-IN": "नमस्ते {name} जी! मैं ArogyaVaani हूँ। आज क्या तकलीफ़ है?",
    "kn-IN": "ನಮಸ್ಕಾರ {name} ಅವರೇ! ನಾನು ArogyaVaani. ಇಂದು ಏನು ತೊಂದರೆ?",
    "en-IN": "Hello {name}! I'm ArogyaVaani. What is troubling you today?",
}
FAILURE = {
    "hi-IN": "एक second, network थोड़ा slow है।",
    "kn-IN": "ಒಂದು ನಿಮಿಷ, ನೆಟ್‌ವರ್ಕ್ ನಿಧಾನವಾಗಿದೆ.",
    "en-IN": "One second, the network is a little slow.",
}
FILLERS = {
    "hi-IN": ["एक second, मैं check कर रही हूँ।", "ज़रा रुकिए, देखती हूँ।", "एक minute, अभी देखती हूँ।"],
    "kn-IN": ["ಒಂದು ನಿಮಿಷ, ನೋಡ್ತೀನಿ.", "ಸ್ವಲ್ಪ ಇರಿ, ಚೆಕ್ ಮಾಡ್ತೀನಿ."],
    "en-IN": ["One second, let me check.", "Just a moment, checking now."],
}
HOLDING = {
    "hi-IN": "आप लाइन पर रहिए, हमारी nurse आपसे जुड़ रही हैं। ज़रूरी हो तो 108 पर call कीजिए।",
    "kn-IN": "ದಯವಿಟ್ಟು ಲೈನ್‌ನಲ್ಲಿ ಇರಿ, ನಮ್ಮ ನರ್ಸ್ ಸೇರಿಕೊಳ್ಳುತ್ತಿದ್ದಾರೆ. ತುರ್ತು ಇದ್ದರೆ 108 ಕ್ಕೆ ಕರೆ ಮಾಡಿ.",
    "en-IN": "Please stay on the line, a nurse is joining. If it is urgent, call 108.",
}
EMERGENCY = {
    "hi-IN": "यह emergency हो सकती है। कृपया अभी 108 पर call कीजिए। मैं appointment रोक रही हूँ और हमारी nurse आपसे जुड़ रही हैं।",
    "kn-IN": "ಇದು ತುರ್ತು ಪರಿಸ್ಥಿತಿ ಆಗಿರಬಹುದು. ದಯವಿಟ್ಟು ಈಗಲೇ 108 ಕ್ಕೆ ಕರೆ ಮಾಡಿ. ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ನಿಲ್ಲಿಸಿದ್ದೇನೆ, ನರ್ಸ್ ಸೇರಿಕೊಳ್ಳುತ್ತಿದ್ದಾರೆ.",
    "en-IN": "This may be an emergency. Please call 108 right now. I am stopping the booking and a nurse is joining you.",
}
RECAP_BOOKED = {
    "hi-IN": "ठीक है, हिंदी में बात करते हैं। आपका {doctor} के साथ {when} का appointment confirm है।",
    "kn-IN": "ಸರಿ, ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ. ನಿಮ್ಮ {doctor} ಅವರ ಜೊತೆ {when} ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಖಚಿತವಾಗಿದೆ.",
    "en-IN": "Sure, let's continue in English. Your appointment with {doctor} on {when} is confirmed.",
}
RECAP_NONE = {
    "hi-IN": "ठीक है, हिंदी में बात करते हैं। आगे बताइए, मैं कैसे मदद करूँ?",
    "kn-IN": "ಸರಿ, ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ. ಹೇಳಿ, ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
    "en-IN": "Sure, let's continue in English. How can I help?",
}
REMINDER_GREETING = {
    "hi-IN": "नमस्ते {name} जी! ArogyaVaani बोल रही हूँ। याद दिलाने के लिए call किया: आपका {doctor} के साथ {when} appointment है। {prep} क्या आपको कुछ पूछना है?",
    "kn-IN": "ನಮಸ್ಕಾರ {name} ಅವರೇ! ArogyaVaani ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ನೆನಪಿಸಲು ಕರೆ ಮಾಡಿದೆ: {doctor} ಅವರ ಜೊತೆ {when} ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಇದೆ. {prep} ಏನಾದರೂ ಕೇಳಬೇಕೇ?",
    "en-IN": "Hello {name}! This is ArogyaVaani with a reminder: you have an appointment with {doctor} on {when}. {prep} Anything you want to ask?",
}
FEEDBACK_GREETING = {
    "hi-IN": "नमस्ते {name} जी! {doctor} के साथ visit कैसी रही? 1 से 5 तक rating दीजिए, पाँच सबसे अच्छा।",
    "kn-IN": "ನಮಸ್ಕಾರ {name} ಅವರೇ! {doctor} ಅವರ ಭೇಟಿ ಹೇಗಿತ್ತು? 1 ರಿಂದ 5 ರೇಟಿಂಗ್ ಕೊಡಿ, ಐದು ಉತ್ತಮ.",
    "en-IN": "Hello {name}! How was your visit with {doctor}? Please give a rating from 1 to 5, five is best.",
}
PREP_DEFAULT = {
    "hi-IN": "अपनी पुरानी रिपोर्ट और X-ray साथ लाइए।",
    "kn-IN": "ದಯವಿಟ್ಟು ಹಳೆಯ ವರದಿ ಮತ್ತು X-ray ತನ್ನಿ.",
    "en-IN": "Please bring your old reports and X-rays.",
}
CONFIRM_MSG = {
    "hi-IN": "ArogyaVaani: आपका appointment confirm है। {doctor}, {clinic}। तारीख़: {date}, समय: {time}। Booking ID: {bid}। {prep}",
    "kn-IN": "ArogyaVaani: ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಖಚಿತವಾಗಿದೆ. {doctor}, {clinic}. ದಿನಾಂಕ: {date}, ಸಮಯ: {time}. Booking ID: {bid}. {prep}",
    "en-IN": "ArogyaVaani: your appointment is confirmed. {doctor}, {clinic}. Date: {date}, time: {time}. Booking ID: {bid}. {prep}",
}
CAREGIVER_MSG = {
    "hi-IN": "ArogyaVaani: {patient} जी का appointment confirm हुआ। {doctor}, {clinic}, {date} {time}। Booking ID: {bid}।",
    "kn-IN": "ArogyaVaani: {patient} ಅವರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಖಚಿತವಾಗಿದೆ. {doctor}, {clinic}, {date} {time}. Booking ID: {bid}.",
    "en-IN": "ArogyaVaani: {patient}'s appointment is confirmed. {doctor}, {clinic}, {date} {time}. Booking ID: {bid}.",
}
VOICE_NOTE = {
    "hi-IN": "आपका appointment {doctor} के साथ {date} को {time} बजे confirm है। {prep}",
    "kn-IN": "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ {doctor} ಅವರ ಜೊತೆ {date} ರಂದು {time} ಕ್ಕೆ ಖಚಿತವಾಗಿದೆ. {prep}",
    "en-IN": "Your appointment with {doctor} on {date} at {time} is confirmed. {prep}",
}

_HI_NUM = ["", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ", "दस", "ग्यारह", "बारह"]
_KN_NUM = ["", "ಒಂದು", "ಎರಡು", "ಮೂರು", "ನಾಲ್ಕು", "ಐದು", "ಆರು", "ಏಳು", "ಎಂಟು", "ಒಂಬತ್ತು", "ಹತ್ತು", "ಹನ್ನೊಂದು", "ಹನ್ನೆರಡು"]


def pick_filler(lang: str) -> str:
    return random.choice(FILLERS.get(lang, FILLERS["hi-IN"]))


def spoken_time(hhmm: str, lang: str) -> str:
    """'10:30' -> 'सुबह साढ़े दस बजे' / 'ಬೆಳಿಗ್ಗೆ ಹತ್ತು ಮೂವತ್ತು' / '10:30 AM'."""
    h, m = (int(x) for x in hhmm.split(":"))
    h12 = h % 12 or 12
    if lang == "en-IN":
        return f"{h12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    if lang == "kn-IN":
        part = "ಬೆಳಿಗ್ಗೆ" if h < 12 else ("ಮಧ್ಯಾಹ್ನ" if h < 16 else "ಸಂಜೆ")
        return f"{part} {_KN_NUM[h12]} ಗಂಟೆ" + (f" {m} ನಿಮಿಷ" if m else "")
    part = "सुबह" if h < 12 else ("दोपहर" if h < 16 else "शाम")
    if m == 30:
        word = {1: "डेढ़", 2: "ढाई"}.get(h12, f"साढ़े {_HI_NUM[h12]}")
        return f"{part} {word} बजे"
    return f"{part} {_HI_NUM[h12]} बजे" if m == 0 else f"{part} {_HI_NUM[h12]} बजकर {m} मिनट"


def spoken_date(iso: str, lang: str) -> str:
    d = date_cls.fromisoformat(iso)
    today = date_cls.today()
    diff = (d - today).days
    if lang == "en-IN":
        return {0: "today", 1: "tomorrow"}.get(diff, d.strftime("%d %b"))
    if lang == "kn-IN":
        return {0: "ಇಂದು", 1: "ನಾಳೆ"}.get(diff, d.strftime("%d-%m"))
    return {0: "आज", 1: "कल"}.get(diff, d.strftime("%d-%m"))


def when_phrase(iso: str, hhmm: str, lang: str) -> str:
    return f"{spoken_date(iso, lang)} {spoken_time(hhmm, lang)}"


def format_template(table: Dict[str, str], lang: str, **kw) -> str:
    return table.get(lang, table["hi-IN"]).format(**kw)


# ---- deterministic voice language-switch detection (no LLM needed for the hot-swap moment)
_LANG_WORDS = {
    "kn-IN": ["kannada", "kannad", "ಕನ್ನಡ"],
    "hi-IN": ["hindi", "हिंदी", "हिन्दी", "ಹಿಂದಿ"],
    "en-IN": ["english", "angrezi", "अंग्रेज़ी", "अंग्रेजी", "ಇಂಗ್ಲಿಷ್", "ಇಂಗ್ಲೀಷ್"],
}
_SWITCH_VERBS = ["maathadi", "mathadi", "matadi", "maatadi", "mathaadi", "baat", "bolo", "speak", "talk", "switch",
                 "change", "बात", "बोलो", "बोलिए", "ಮಾತನಾಡಿ", "ಮಾತಾಡಿ", "ಮಾತಾಡು", "ಮಾತನಾಡು", "kijiye", "karo", "karein"]
_DOCTOR_WORDS = ["doctor", "dr.", "dr ", "डॉक्टर", "ವೈದ್ಯ", "ಡಾಕ್ಟರ್", "clinic", "डॉ"]


def detect_language_request(text: str):
    """Return 'hi-IN' | 'kn-IN' | 'en-IN' if the user asks to change the conversation language, else None.
    'doctor jo Kannada bolta ho' is a doctor preference, not a switch request."""
    t = (text or "").lower()
    if not t or any(w in t for w in _DOCTOR_WORDS):
        return None
    if not any(v in t for v in _SWITCH_VERBS):
        return None
    hits = [lang for lang, words in _LANG_WORDS.items() if any(w in t for w in words)]
    return hits[0] if len(hits) == 1 else None


SWITCH_ACK = {
    "hi-IN": "ठीक है, हिंदी में बात करते हैं।",
    "kn-IN": "ಸರಿ, ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ.",
    "en-IN": "Sure, let's continue in English.",
}
