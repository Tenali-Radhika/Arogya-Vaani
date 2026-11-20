"""
ArogyaVaani brain: OpenAI-compatible /chat/completions endpoint that Agora ConvoAI calls.

Agora sends the transcript; this endpoint runs a multi-step tool loop (up to 6 rounds) against our own
LLM provider and streams ONLY spoken text back as OpenAI SSE chunks. Agora never sees a tool_call.
Deliberately free of any agora-agents import (provider-agnostic, per AGENTS.md).
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional
from zoneinfo import ZoneInfo

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_base_dir, ".env.local"), override=False)
load_dotenv(os.path.join(_base_dir, ".env"), override=False)

import db  # noqa: E402
import i18n  # noqa: E402
import llm_client  # noqa: E402
import triage as triage_mod  # noqa: E402
from events import hub  # noqa: E402
from http_util import METRICS  # noqa: E402
from tools import handlers  # noqa: E402,F401  (registers tools)
from tools.registry import ToolContext, run_tool, schemas  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_SENTENCES = 2
TURN_LATENCY_MS: List[float] = []  # per-turn total, for the p50 badge
SWAP_DELAY_S = 1.5

app = FastAPI(title="ArogyaVaani LLM endpoint", version="2.0.0",
              description="OpenAI-compatible Chat Completions with an internal tool loop for Agora ConvoAI.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_SCRIPT_RULES = {
    "hi-IN": "write Hindi in Devanagari; keep English medical words and doctor names (Dr.) in Latin script.",
    "kn-IN": "write Kannada in Kannada script; keep English medical words and doctor names (Dr.) in Latin script.",
    "en-IN": "simple Indian English.",
}


# ----------------------------------------------------------------------------- helpers
class SentenceCap:
    """Stops output after N sentences and strips markdown noise. Handles 'Dr.' and decimals."""
    ABBR = {"dr", "mr", "mrs", "ms", "no", "rs"}

    def __init__(self, n: int = MAX_SENTENCES):
        self.n, self.count, self.done = n, 0, False
        self._pending_term = False
        self._word = ""

    def feed(self, chunk: str) -> str:
        out = []
        chunk = re.sub(r"[*#`_]|\[[^\]]*\]", "", chunk)
        for ch in chunk:
            if self.done:
                break
            if self._pending_term:
                self._pending_term = False
                if ch.isspace() and self._word.lower() not in self.ABBR:
                    self.count += 1
                    if self.count >= self.n:
                        self.done = True
                        break
            if ch in ".?!।":
                self._pending_term = True
            if ch.isalpha():
                self._word += ch
            elif not ch.isdigit() and ch not in ".":
                self._word = ""
            out.append(ch)
        return "".join(out)

    def flush_end(self) -> None:
        pass


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return ""


def parse_session_info(messages: List[dict]) -> Dict[str, str]:
    info = {"session": "default", "lang": "hi-IN", "patient": ""}
    for m in messages:
        if m.get("role") == "system":
            txt = _content_text(m.get("content"))
            for key in info:
                mm = re.search(rf"{key}=([\w\-:.]+)", txt)
                if mm:
                    info[key] = mm.group(1)
    return info


def patient_context(patient_id: str, session_id: str) -> str:
    p = db.get_patient(patient_id)
    cs = db.get_call_session(session_id)
    lines = []
    if p and p.name:
        lines.append(f"PATIENT: {p.name}, age {p.age or 'unknown'}, area {p.area or 'unknown'}, languages {p.languages}, "
                     f"preferred {p.preferred_lang}, caregiver {'yes' if p.caregiver_phone else 'no'}.")
        if p.elder_mode:
            lines.append("ELDER MODE: speak slowly and simply, one idea per sentence.")
    else:
        lines.append("PATIENT: new or unidentified. Greeting done; ask name, area, language one at a time.")
    if cs.summary:
        bid, did, d, t = (cs.summary.split("|") + ["", "", "", ""])[:4]
        lines.append(f"CURRENT BOOKING: id {bid}, doctor_id {did}, date {d}, time {t}.")
    if cs.escalated:
        lines.append(f"ESCALATION OPEN: {cs.escalation_reason}. Do not book.")
    return "\n".join(lines)


def build_system_prompt(patient_id: str, session_id: str, lang: str, extra: str = "") -> str:
    extra = extra or db.get_call_session(session_id).note
    with open(os.path.join(os.path.dirname(__file__), "prompts", "system.md"), encoding="utf-8") as f:
        tpl = f.read()
    cs = db.get_call_session(session_id)
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return (tpl.replace("{{LANG_NAME}}", i18n.LANG_NAMES.get(lang, "Hindi"))
            .replace("{{SCRIPT_RULE}}", _SCRIPT_RULES.get(lang, _SCRIPT_RULES["hi-IN"]))
            .replace("{{NOW}}", now.strftime("%A %Y-%m-%d %H:%M IST"))
            .replace("{{STAGE}}", cs.stage)
            .replace("{{PATIENT_CONTEXT}}", patient_context(patient_id, session_id))
            .replace("{{EXTRA}}", extra))


def _history(messages: List[dict], limit: int = 24) -> List[dict]:
    out = []
    for m in messages:
        role = m.get("role")
        if role in ("user", "assistant"):
            text = _content_text(m.get("content")).strip()
            if text:
                out.append({"role": role, "content": text})
    return out[-limit:]


def p50(values: List[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    return s[len(s) // 2]


# ----------------------------------------------------------------------------- the turn
async def agent_turn(session_id: str, lang: str, patient_id: str, messages: List[dict],
                     extra_prompt: str = "") -> AsyncIterator[str]:
    """Yield spoken text pieces for one user turn."""
    t_start = time.perf_counter()
    cs = db.get_call_session(session_id)
    if cs.lang != lang or (patient_id and cs.patient_id != patient_id):
        cs = db.update_call_session(session_id, lang=lang, patient_id=patient_id or cs.patient_id)
    patient_id = cs.patient_id
    ctx = ToolContext(session_id=session_id, patient_id=patient_id, lang=lang)
    hist = _history(messages)
    user_text = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
    if user_text:
        db.add_transcript(session_id, "user", user_text, lang)
        hub.publish(session_id, {"type": "transcript", "role": "user", "text": user_text, "lang": lang})

    spoken: List[str] = []

    def emit(text: str) -> str:
        spoken.append(text)
        return text

    try:
        # 1. Human takeover in progress: holding line only, never book.
        if db.get_call_session(session_id).escalated:
            yield emit(i18n.HOLDING.get(lang, i18n.HOLDING["hi-IN"]))
            return
        # 2. Deterministic red-flag gate BEFORE the LLM (fast, cannot be talked out of).
        flag = triage_mod.detect_red_flag(user_text)
        if flag:
            await run_tool(ctx, "escalate_to_human", {"reason": flag})
            yield emit(i18n.EMERGENCY.get(lang, i18n.EMERGENCY["hi-IN"]))
            return

        convo = [{"role": "system", "content": build_system_prompt(patient_id, session_id, lang, extra_prompt)}] + hist
        tool_ms = 0.0
        ttft_ms: Optional[float] = None
        filler_sent = False
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            cap = SentenceCap()
            text_parts: List[str] = []
            calls: List[dict] = []
            use_tools = schemas() if round_no < MAX_TOOL_ROUNDS else None
            async for ev in llm_client.stream_chat(convo, use_tools):
                if ev["type"] == "ttft" and ttft_ms is None:
                    ttft_ms = ev["ms"]
                elif ev["type"] == "text":
                    piece = cap.feed(ev["text"])
                    if piece:
                        text_parts.append(piece)
                        yield emit(piece)
                elif ev["type"] == "tool_calls":
                    calls = ev["calls"]
            if not calls:
                break
            if not filler_sent and not text_parts:
                filler_sent = True
                yield emit(i18n.pick_filler(lang) + " ")
            convo.append({"role": "assistant", "content": "".join(text_parts) or None,
                          "tool_calls": [{"id": c["id"] or f"call_{i}", "type": "function",
                                          "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                                         for i, c in enumerate(calls)]})
            t0 = time.perf_counter()

            async def _one(c, idx):
                try:
                    args = json.loads(c["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                res = await run_tool(ctx, c["name"], args)
                return {"role": "tool", "tool_call_id": c["id"] or f"call_{idx}",
                        "content": json.dumps(res, ensure_ascii=False)[:3500]}

            results = await asyncio.gather(*[_one(c, i) for i, c in enumerate(calls)])
            tool_ms += (time.perf_counter() - t0) * 1000
            convo.extend(results)
            if db.get_call_session(session_id).escalated and any(c["name"] == "triage_symptoms" for c in calls):
                yield emit(i18n.EMERGENCY.get(lang, i18n.EMERGENCY["hi-IN"]))
                return
    except Exception as e:
        logger.exception("agent_turn failed")
        hub.publish(session_id, {"type": "error", "text": f"{type(e).__name__}: {e}"})
        if not spoken:
            yield emit(i18n.FAILURE.get(lang, i18n.FAILURE["hi-IN"]))
    finally:
        total = (time.perf_counter() - t_start) * 1000
        TURN_LATENCY_MS.append(total)
        del TURN_LATENCY_MS[:-200]
        reply = "".join(spoken).strip()
        if reply:
            db.add_transcript(session_id, "assistant", reply, lang)
            hub.publish(session_id, {"type": "transcript", "role": "assistant", "text": reply, "lang": lang})
        hub.publish(session_id, {"type": "turn_metrics", "total_ms": round(total), "p50_ms": round(p50(TURN_LATENCY_MS) or 0)})
        target = handlers.PENDING_SWAPS.pop(session_id, None)
        if target and handlers.HOOKS.get("request_swap"):
            asyncio.get_event_loop().call_later(
                SWAP_DELAY_S, lambda: asyncio.ensure_future(handlers.HOOKS["request_swap"](session_id, target)))


# ----------------------------------------------------------------------------- SSE plumbing
def make_chunk(chunk_id: str, model: str, content: str, finish_reason=None) -> str:
    chunk = {"id": chunk_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model or "arogya-agent",
             "choices": [{"index": 0, "delta": {"content": content} if content else {}, "finish_reason": finish_reason}]}
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def make_role_chunk(chunk_id: str, model: str) -> str:
    chunk = {"id": chunk_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model or "arogya-agent",
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _check_auth(authorization: Optional[str]) -> None:
    expected = os.getenv("CUSTOM_LLM_API_KEY")
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid bearer token")


@app.post("/chat/completions")
async def chat_completions(request: Request, authorization: Optional[str] = Header(None, alias="Authorization")):
    _check_auth(authorization)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages required")
    if body.get("stream") is False:
        raise HTTPException(status_code=400, detail="Only streaming mode is supported. Set stream=true.")
    info = parse_session_info(messages)
    lang = i18n.normalize_lang(info["lang"])
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    model = body.get("model") or "arogya-agent"
    logger.info("llm request session=%s lang=%s msgs=%d", info["session"], lang, len(messages))

    async def generate():
        yield make_role_chunk(chunk_id, model)
        async for piece in agent_turn(info["session"], lang, info["patient"], messages):
            yield make_chunk(chunk_id, model, piece)
        yield make_chunk(chunk_id, model, "", finish_reason="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "arogyavaani-llm", "llm_configured": llm_client.configured()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
