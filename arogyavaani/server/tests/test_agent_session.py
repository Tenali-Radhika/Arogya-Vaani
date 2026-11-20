"""Join payload per language + lifecycle (hot swap, speak) with a fake Agora session."""
import pytest

import agent_session as a
import db
import i18n
from events import hub


@pytest.mark.parametrize("lang", ["hi-IN", "kn-IN", "en-IN"])
def test_join_payload_shape(lang, monkeypatch):
    monkeypatch.setenv("MURF_API_KEY", "mk")
    monkeypatch.setenv("MURF_VOICE_ID", "Neeta")
    p = a.manager.build_join_payload("sess1", lang, patient_id="p1")
    assert p["asr"]["vendor"] == "sarvam" and p["asr"]["params"]["language"] == lang
    tts = p["tts"]
    assert tts["vendor"] == "murf"
    assert tts["params"] | {} == {"api_key": "mk", "base_url": "wss://in.api.murf.ai/v1/speech/stream-input",
                                   "voiceId": "Neeta", "locale": lang, "rate": 0, "pitch": 0, "model": "FALCON",
                                   "sample_rate": 24000}
    assert p["llm"]["url"].endswith("/llm/chat/completions") and p["llm"]["vendor"] == "custom"
    assert p["llm"]["system_messages"][0]["content"] == f"session=sess1;lang={lang};patient=p1"
    assert p["llm"]["greeting_message"] == i18n.GREETING[lang]
    assert p["advanced_features"] == {"enable_rtm": True, "enable_tools": False}
    assert p["parameters"]["data_channel"] == "rtm" and p["parameters"]["enable_metrics"] is True
    assert p["idle_timeout"] == 120
    assert p["turn_detection"]["config"]["start_of_speech"]["mode"] == "vad"  # interruptions on


def test_same_voice_all_languages_and_elder_rate(monkeypatch):
    monkeypatch.setenv("MURF_VOICE_ID", "Neeta")
    voices = {a.manager.build_join_payload("s", l)["tts"]["params"]["voiceId"] for l in i18n.LANGS}
    assert voices == {"Neeta"}
    assert a.manager.build_join_payload("s", "hi-IN", elder_mode=True)["tts"]["params"]["rate"] == -10


def test_ares_fallback_switch(monkeypatch):
    monkeypatch.setenv("ASR_VENDOR", "ares")
    p = a.manager.build_join_payload("s", "hi-IN")
    assert p["asr"]["vendor"] == "ares" and p["asr"]["params"]["language"] == "en-IN,hi-IN"


def test_redact_hides_secrets(monkeypatch):
    monkeypatch.setenv("MURF_API_KEY", "super-secret")
    red = a.redact(a.manager.build_join_payload("s", "hi-IN"))
    assert "super-secret" not in str(red) and "sarvam-test" not in str(red)


def test_truncate_utf8_limit():
    long = "यह एक बहुत लंबा वाक्य है। " * 40
    out = a.truncate_utf8(long)
    assert len(out.encode()) <= 512 and out
    assert a.truncate_utf8("short") == "short"


class FakeSess:
    def __init__(self):
        self.said, self.stopped = [], False

    async def say(self, text, priority=None):
        self.said.append((text, priority))

    async def stop(self):
        self.stopped = True


def _live(mgr, sid="s1", lang="hi-IN"):
    mgr.live[sid] = {"session": FakeSess(), "agent_id": "ag1", "channel": "ch", "agent_uid": 1, "user_uid": 2,
                     "lang": lang, "elder": False, "patient_id": "p1"}


async def test_speak_enforces_priority_and_size():
    m = a.AgentSessionManager()
    _live(m)
    r = await m.speak("s1", "नमस्ते " * 200, "append")
    assert r["bytes"] <= 512 and m.live["s1"]["session"].said[0][1] == "APPEND"
    with pytest.raises(ValueError):
        await m.speak("s1", "x", "LOUD")
    with pytest.raises(ValueError):
        await m.speak("s1", "   ")
    with pytest.raises(ValueError):
        await m.speak("nope", "hi")


async def test_hot_swap_restarts_with_new_lang_and_recap(monkeypatch):
    m = a.AgentSessionManager()
    _live(m)
    db.upsert_patient("p1", name="Lakshmi")
    db.update_call_session("s1", summary="BK1|doc01|2030-01-02|10:30")
    started = {}

    async def fake_start(sid, channel, agent_uid, user_uid, lang, patient_id, elder, greeting=None, codec=None):
        started.update(sid=sid, channel=channel, lang=lang, greeting=greeting, patient=patient_id)
        m.live[sid] = {"session": FakeSess(), "agent_id": "ag2", "channel": channel, "agent_uid": agent_uid,
                       "user_uid": user_uid, "lang": lang, "elder": elder, "patient_id": patient_id}
    monkeypatch.setattr(m, "start", fake_start)
    old = m.live["s1"]["session"]
    res = await m.hot_swap("s1", "Kannada")
    assert res["swapped"] and res["lang"] == "kn-IN" and old.stopped
    assert started["channel"] == "ch" and started["lang"] == "kn-IN"
    assert "Suresh Rao" in started["greeting"]  # memory survived the swap: booking recap in Kannada
    assert db.get_patient("p1").preferred_lang == "kn-IN"
    assert any(e["type"] == "language_swap" and e.get("phase") == "done" for e in hub.recent("s1"))
    assert (await m.hot_swap("s1", "kn-IN"))["swapped"] is False


def test_spoken_time_phrases():
    assert i18n.spoken_time("10:30", "hi-IN") == "सुबह साढ़े दस बजे"
    assert i18n.spoken_time("15:00", "en-IN") == "3:00 PM"
    assert i18n.spoken_time("09:00", "kn-IN").startswith("ಬೆಳಿಗ್ಗೆ")


async def test_force_swap_applies_elder_rate(monkeypatch):
    m = a.AgentSessionManager()
    _live(m)
    seen = {}

    async def fake_start(sid, channel, agent_uid, user_uid, lang, patient_id, elder, greeting=None, codec=None):
        seen["lang"], seen["elder"] = lang, elder
        _live(m, sid, lang)
    monkeypatch.setattr(m, "start", fake_start)
    m.live["s1"]["elder"] = True
    res = await m.hot_swap("s1", "hi-IN", force=True)
    assert res["swapped"] and seen == {"lang": "hi-IN", "elder": True}
