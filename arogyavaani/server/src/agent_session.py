"""Single owner of the Agora ConvoAI agent lifecycle: start, stop, speak, language hot-swap.

ASR/TTS cannot be changed on a live agent (the update API only covers token + llm fields), so a language
switch = leave + re-join with the new Sarvam language and Murf Falcon locale. Memory survives because the
conversation state lives in our DB keyed by session_id / patient_id.
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

from agora_agent import Area, AsyncAgora
from agora_agent.agentkit import Agent as AgoraAgent
from agora_agent.agentkit.vendors import AresSTT, CustomLLM, MurfTTS, SarvamSTT

import db
import directory
import i18n
from events import hub

logger = logging.getLogger("arogya.session")

ELDER_RATE = -10
SPEAK_MAX_BYTES = 512
PRIORITIES = ("INTERRUPT", "APPEND", "IGNORE")

LANG_PROFILES: Dict[str, Dict[str, Any]] = {
    lang: {"asr_language": lang, "murf_locale": lang, "greeting": i18n.GREETING[lang],
           "failure_message": i18n.FAILURE[lang], "elder_rate_offset": ELDER_RATE}
    for lang in i18n.LANGS
}


def truncate_utf8(text: str, max_bytes: int = SPEAK_MAX_BYTES) -> str:
    b = text.encode("utf-8")
    if len(b) <= max_bytes:
        return text
    cut = b[:max_bytes].decode("utf-8", errors="ignore")
    # prefer cutting at a sentence/word boundary
    for sep in ("।", ".", "?", "!", " "):
        i = cut.rfind(sep)
        if i > len(cut) // 2:
            return cut[: i + 1].strip()
    return cut


def redact(obj: Any) -> Any:
    """Copy of a join payload with every secret replaced (for README / logs)."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in ("api_key", "token", "key") else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


class AgentSessionManager:
    def __init__(self) -> None:
        self.live: Dict[str, Dict[str, Any]] = {}   # session_id -> state incl. SDK session
        self._client: Optional[AsyncAgora] = None

    # ----------------------------------------------------------------- config
    @staticmethod
    def _env(name: str, default: str = "") -> str:
        return os.getenv(name, default)

    @property
    def client(self) -> AsyncAgora:
        if self._client is None:
            self._client = AsyncAgora(area=Area.US, app_id=self._env("AGORA_APP_ID"),
                                      app_certificate=self._env("AGORA_APP_CERTIFICATE"))
        return self._client

    def _stt(self, lang: str):
        prof = LANG_PROFILES[lang]
        if self._env("ASR_VENDOR", "sarvam") == "ares":
            return AresSTT(additional_params={"language": "en-IN,hi-IN"})
        return SarvamSTT(api_key=self._env("SARVAM_API_KEY", "missing"), language=prof["asr_language"])

    def _tts(self, lang: str, elder_mode: bool):
        prof = LANG_PROFILES[lang]
        return MurfTTS(key=self._env("MURF_API_KEY", "missing"), voice_id=self._env("MURF_VOICE_ID") or None,
                       base_url=self._env("MURF_BASE_URL", "wss://in.api.murf.ai/v1/speech/stream-input"),
                       locale=prof["murf_locale"], model="FALCON", sample_rate=24000, pitch=0,
                       rate=prof["elder_rate_offset"] if elder_mode else 0)

    def build_agent(self, session_id: str, lang: str, elder_mode: bool = False, patient_id: str = "",
                    greeting: Optional[str] = None, output_audio_codec: Optional[str] = None) -> AgoraAgent:
        prof = LANG_PROFILES[lang]
        llm = CustomLLM(base_url=self._env("CUSTOM_LLM_URL"), api_key=self._env("CUSTOM_LLM_API_KEY", "any-key-here"),
                        model=self._env("CUSTOM_LLM_MODEL", "arogya-agent"),
                        system_messages=[{"role": "system",
                                          "content": f"session={session_id};lang={lang};patient={patient_id or 'anon'}"}],
                        greeting_message=greeting or prof["greeting"], failure_message=prof["failure_message"],
                        max_history=32, max_tokens=400, temperature=0.4)
        parameters: Dict[str, Any] = {"audio_scenario": "chorus", "data_channel": "rtm",
                                      "enable_error_message": True, "enable_metrics": True}
        if output_audio_codec:
            parameters["output_audio_codec"] = output_audio_codec
        agent = AgoraAgent(
            client=self.client,
            turn_detection={"config": {"speech_threshold": 0.5,
                                       "start_of_speech": {"mode": "vad", "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300}},
                                       "end_of_speech": {"mode": "vad", "vad_config": {"silence_duration_ms": 480}}}},
            advanced_features={"enable_rtm": True, "enable_tools": False},
            parameters=parameters)
        return agent.with_stt(self._stt(lang)).with_llm(llm).with_tts(self._tts(lang, elder_mode))

    def build_join_payload(self, session_id: str, lang: str, elder_mode: bool = False, channel: str = "ch-test",
                           agent_uid: int = 1001, user_uid: int = 2001, patient_id: str = "",
                           greeting: Optional[str] = None) -> Dict[str, Any]:
        """The exact `properties` object sent to ConvoAI join (token redacted). Used by tests and the README."""
        agent = self.build_agent(session_id, lang, elder_mode, patient_id, greeting)
        sess = agent.create_async_session(channel=channel, agent_uid=str(agent_uid), remote_uids=[str(user_uid)],
                                          enable_string_uid=False, idle_timeout=120, token="<redacted>")
        props = sess._build_start_properties({"token": "<redacted>"}, frozenset(), frozenset())  # noqa: SLF001
        return props

    # ----------------------------------------------------------------- lifecycle
    async def start(self, session_id: str, channel: str, agent_uid: int, user_uid: int, lang: str = "hi-IN",
                    patient_id: str = "", elder_mode: bool = False, greeting: Optional[str] = None,
                    output_audio_codec: Optional[str] = None) -> Dict[str, Any]:
        lang = i18n.normalize_lang(lang)
        if not channel or agent_uid <= 0 or user_uid <= 0:
            raise ValueError("channel, agent_uid and user_uid are required")
        if not self._env("CUSTOM_LLM_URL"):
            raise ValueError("CUSTOM_LLM_URL is required (public URL of /llm/chat/completions)")
        agent = self.build_agent(session_id, lang, elder_mode, patient_id, greeting, output_audio_codec)
        sess = agent.create_async_session(channel=channel, agent_uid=str(agent_uid), remote_uids=[str(user_uid)],
                                          enable_string_uid=False, idle_timeout=120, expires_in=3600,
                                          name=f"arogya-{session_id}"[:60])
        t0 = time.perf_counter()
        agent_id = await sess.start()
        ms = (time.perf_counter() - t0) * 1000
        self.live[session_id] = {"session": sess, "agent_id": agent_id, "channel": channel, "agent_uid": agent_uid,
                                 "user_uid": user_uid, "lang": lang, "elder": elder_mode, "patient_id": patient_id}
        db.update_call_session(session_id, lang=lang, agent_id=agent_id, channel=channel,
                               patient_id=patient_id or "anon")
        logger.info("started agent session=%s agent_id=%s lang=%s ms=%d", session_id, agent_id, lang, ms)
        hub.publish(session_id, {"type": "agent_started", "agent_id": agent_id, "lang": lang, "ms": round(ms)})
        return {"agent_id": agent_id, "channel_name": channel, "status": "started", "lang": lang, "session_id": session_id}

    async def stop(self, session_id: str) -> None:
        st = self.live.pop(session_id, None)
        if not st:
            return
        try:
            await st["session"].stop()
        except Exception:
            logger.warning("stop failed; falling back to client.stop_agent", exc_info=True)
            await self.client.stop_agent(st["agent_id"])
        hub.publish(session_id, {"type": "agent_stopped"})

    async def speak(self, session_id: str, text: str, priority: str = "INTERRUPT") -> Dict[str, Any]:
        st = self.live.get(session_id)
        if not st:
            raise ValueError("no live agent for this session")
        priority = priority.upper()
        if priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
        text = truncate_utf8((text or "").strip())
        if not text:
            raise ValueError("text is empty")
        await st["session"].say(text, priority=priority)
        return {"ok": True, "spoken": text, "bytes": len(text.encode("utf-8"))}

    # ----------------------------------------------------------------- hot swap
    @staticmethod
    def recap(session_id: str, lang: str) -> str:
        cs = db.get_call_session(session_id)
        if cs.summary:
            bid, did, d, t = (cs.summary.split("|") + ["", "", "", ""])[:4]
            doc = directory.get_doctor(did)
            if doc and d and t:
                return i18n.format_template(i18n.RECAP_BOOKED, lang, doctor=doc["name"], when=i18n.when_phrase(d, t, lang))
        return i18n.RECAP_NONE[lang]

    async def hot_swap(self, session_id: str, new_lang: str) -> Dict[str, Any]:
        new_lang = i18n.normalize_lang(new_lang)
        st = self.live.get(session_id)
        if not st:
            raise ValueError("no live agent for this session")
        if st["lang"] == new_lang:
            return {"ok": True, "swapped": False, "lang": new_lang}
        t0 = time.perf_counter()
        hub.publish(session_id, {"type": "language_swap", "phase": "start", "from": st["lang"], "to": new_lang})
        keep = {k: st[k] for k in ("channel", "agent_uid", "user_uid", "elder", "patient_id")}
        await self.stop(session_id)
        db.update_call_session(session_id, lang=new_lang)
        if keep["patient_id"]:
            db.upsert_patient(keep["patient_id"], preferred_lang=new_lang)
        await self.start(session_id, keep["channel"], keep["agent_uid"], keep["user_uid"], new_lang,
                         keep["patient_id"], keep["elder"], greeting=self.recap(session_id, new_lang))
        ms = (time.perf_counter() - t0) * 1000
        logger.info("language hot-swap session=%s to=%s ms=%d", session_id, new_lang, ms)
        hub.publish(session_id, {"type": "language_swap", "phase": "done", "to": new_lang, "ms": round(ms)})
        return {"ok": True, "swapped": True, "lang": new_lang, "ms": round(ms)}


manager = AgentSessionManager()
