import pytest

from triage import classify_specialty, detect_red_flag, triage

RED = [
    "mujhe seene mein dard ho raha hai", "मुझे सीने में दर्द है", "ನನಗೆ ಎದೆ ನೋವು ಇದೆ", "I have chest pain",
    "saans nahi aa rahi", "सांस लेने में तकलीफ है", "ಉಸಿರಾಟದ ತೊಂದರೆ ಇದೆ", "bahut khoon aa raha hai",
    "बहुत खून बह रहा है", "ತುಂಬಾ ರಕ್ತ ಬರುತ್ತಿದೆ", "munh tedha ho gaya", "मुंह टेढ़ा हो गया है", "main marna chahta hoon",
    "मैं आत्महत्या करना चाहता हूँ", "ನಾನು ಆತ್ಮಹತ್ಯೆ ಮಾಡಿಕೊಳ್ಳಬೇಕು", "pregnant hoon aur bleeding ho rahi hai",
    "नवजात बच्चे को बुखार है",
]


@pytest.mark.parametrize("text", RED)
def test_red_flags_detected(text):
    assert detect_red_flag(text), text
    r = triage(text)
    assert r["red_flag"] and r["specialty"] is None


@pytest.mark.parametrize("text,spec", [
    ("Mere ghutne mein bahut dard hai, chalne mein problem ho rahi hai", "orthopaedics"),
    ("मेरी आंख में जलन है", "ophthalmology"),
    ("ನನಗೆ ತಲೆನೋವು ಮತ್ತು ಜ್ವರ ಇದೆ", "general physician"),
    ("kaan mein dard hai", "ENT"),
    ("sugar high rehta hai", "diabetology"),
])
def test_specialty_routing(text, spec):
    got, _ = classify_specialty(text)
    assert got == spec
    assert not detect_red_flag(text)


def test_hint_used_when_no_keyword():
    assert classify_specialty("kuch ajeeb sa lag raha hai", hint="cardiology") == ("cardiology", "hint")
    assert classify_specialty("kuch ajeeb sa lag raha hai")[0] == "general physician"
