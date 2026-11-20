"""Deterministic triage: red-flag matcher (hi/kn/en, Roman + native script) and symptom -> specialty.

NEVER a diagnosis. Red flags always win over specialty routing.
"""
import re
from typing import Dict, List, Optional, Tuple

# category -> (single phrases, combos of (set_a, set_b) where one of each must appear)
RED_FLAGS: Dict[str, dict] = {
    "chest_pain": {"any": [
        "chest pain", "heart attack", "seene mein dard", "seene me dard", "seene mein bahut dard", "sine mein dard",
        "chest mein dard", "सीने में दर्द", "सीने में तेज दर्द", "सीने मे दर्द", "छाती में दर्द",
        "ಎದೆ ನೋವು", "ಎದೆನೋವು", "ede novu", "yede novu", "edhe novu", "ಎದೆಯಲ್ಲಿ ನೋವು"]},
    "breathing": {"any": [
        "can't breathe", "cannot breathe", "difficulty breathing", "breathing difficulty", "short of breath",
        "saans nahi", "saans lene mein", "saans phool", "dam phool", "सांस नहीं", "सांस लेने में", "साँस लेने में", "सांस फूल",
        "ಉಸಿರಾಟದ ತೊಂದರೆ", "ಉಸಿರು ಕಟ್ಟ", "usiraata", "usirata", "usiru kattu"]},
    "stroke": {"any": [
        "face drooping", "slurred speech", "one side weak", "stroke", "chehra tedha", "munh tedha", "ek taraf kamzor",
        "bolne mein dikkat", "लकवा", "मुंह टेढ़ा", "चेहरा टेढ़ा", "एक तरफ कमजोर", "बोलने में दिक्कत",
        "ಪಾರ್ಶ್ವವಾಯು", "ಮುಖ ಓರೆ", "ಮಾತು ಅಸ್ಪಷ್ಟ"]},
    "bleeding": {"any": [
        "heavy bleeding", "bleeding a lot", "bahut khoon", "khoon band nahi", "बहुत खून", "खून बंद नहीं", "ज्यादा खून",
        "ತುಂಬಾ ರಕ್ತ", "ರಕ್ತಸ್ರಾವ ನಿಲ್ಲ", "tumba rakta"]},
    "suicidal": {"any": [
        "suicide", "kill myself", "end my life", "marna chahta", "marna chahti", "jaan dena", "aatmahatya",
        "मरना चाहता", "मरना चाहती", "जान देना", "आत्महत्या", "ಆತ್ಮಹತ್ಯೆ", "ಸಾಯಬೇಕು", "saayabeku"]},
    "unconscious": {"any": [
        "unconscious", "fainted", "behosh", "बेहोश", "ಪ್ರಜ್ಞೆ ತಪ್ಪ", "ಮೂರ್ಛೆ"]},
    "pregnancy_bleeding": {"combo": (
        ["pregnant", "pregnancy", "garbh", "pet se", "गर्भ", "प्रेग्नेंट", "ಗರ್ಭ"],
        ["bleeding", "khoon", "blood", "खून", "रक्त", "ರಕ್ತ"])},
    "infant_fever": {"combo": (
        ["infant", "newborn", "navjaat", "nawjaat", "mahine ka baby", "month old", "नवजात", "महीने का बच्चा", "ಹಸುಗೂಸು", "ನವಜಾತ"],
        ["fever", "bukhar", "temperature", "बुखार", "ಜ್ವರ"])},
}

SPECIALTY_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("orthopaedics", ["knee", "ghutne", "ghutna", "ghutnon", "घुटने", "घुटना", "joint", "jodo", "जोड़", "back pain", "kamar dard",
                      "कमर", "fracture", "haddi", "हड्डी", "walking", "chalne", "चलने", "ಮೊಣಕಾಲು", "monakalu", "ಕೀಲು", "ಬೆನ್ನು ನೋವು", "bennu novu"]),
    ("cardiology", ["palpitation", "dhadkan", "धड़कन", "high bp", "blood pressure", "bp ", "ಹೃದಯ", "hrudaya"]),
    ("diabetology", ["sugar", "diabetes", "मधुमेह", "शुगर", "ಸಕ್ಕರೆ ಕಾಯಿಲೆ", "ಮಧುಮೇಹ"]),
    ("paediatrics", ["bachcha", "baccha", "bachche", "child", "baby", "kid", "बच्चा", "बच्चे", "ಮಗು", "magu"]),
    ("gynaecology", ["period", "pregnan", "garbh", "mahavari", "गर्भ", "माहवारी", "ಮುಟ್ಟು", "ಗರ್ಭ"]),
    ("dermatology", ["skin", "rash", "khujli", "itch", "pimple", "twacha", "त्वचा", "खुजली", "ಚರ್ಮ", "ತುರಿಕೆ"]),
    ("ENT", ["ear", "kaan", "throat", "gala", "nose", "naak", "कान", "गला", "नाक", "ಕಿವಿ", "ಗಂಟಲು", "ಮೂಗು"]),
    ("ophthalmology", ["eye", "aankh", "ankh", "vision", "आंख", "आँख", "ಕಣ್ಣು"]),
    ("general physician", ["fever", "bukhar", "cold", "cough", "khansi", "headache", "sar dard", "बुखार", "खांसी", "सर दर्द", "ಜ್ವರ", "ಕೆಮ್ಮು", "ತಲೆನೋವು"]),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def detect_red_flag(text: str) -> Optional[str]:
    t = _norm(text)
    if not t:
        return None
    for cat, spec in RED_FLAGS.items():
        if any(p in t for p in spec.get("any", [])):
            return cat
        combo = spec.get("combo")
        if combo and any(a in t for a in combo[0]) and any(b in t for b in combo[1]):
            return cat
    return None


def classify_specialty(text: str, hint: Optional[str] = None) -> Tuple[str, str]:
    """Return (specialty, how) where how in {keyword, hint, default}."""
    t = _norm(text)
    scores = []
    for spec, kws in SPECIALTY_KEYWORDS:
        n = sum(1 for k in kws if k in t)
        if n:
            scores.append((n, spec))
    if scores:
        scores.sort(key=lambda x: -x[0])
        return scores[0][1], "keyword"
    if hint:
        return hint, "hint"
    return "general physician", "default"


def triage(symptoms: str, specialty_hint: Optional[str] = None) -> dict:
    flag = detect_red_flag(symptoms)
    if flag:
        return {"red_flag": True, "category": flag, "urgency": "emergency", "specialty": None,
                "advice": "Call 108 now. Do not book an appointment."}
    spec, how = classify_specialty(symptoms, specialty_hint)
    return {"red_flag": False, "urgency": "routine", "specialty": spec, "matched_by": how,
            "note": "Guidance only, not a diagnosis."}
