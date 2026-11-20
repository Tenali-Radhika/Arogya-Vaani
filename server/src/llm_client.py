"""OpenAI-compatible streaming chat client with tool calling and primary->secondary failover.

Env:
  LLM_BASE_URL (default https://api.openai.com/v1)  LLM_API_KEY (or OPENAI_API_KEY)  LLM_MODEL (default gpt-4o-mini)
  LLM_FALLBACK_MODEL [+ LLM_FALLBACK_BASE_URL / LLM_FALLBACK_API_KEY]  - used when the primary fails before first token.
Anthropic and Amazon Bedrock both expose OpenAI-compatible endpoints, so they work by changing the base URL/model.
Tests monkeypatch `stream_chat`.
"""
import json
import logging
import os
import time
from typing import AsyncIterator, Dict, List, Optional

import httpx

import http_util

logger = logging.getLogger("arogya.llm")


def _cfg(prefix: str = "") -> Optional[dict]:
    if prefix:
        model = os.getenv("LLM_FALLBACK_MODEL")
        if not model:
            return None
        return {"base": (os.getenv("LLM_FALLBACK_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
                "key": os.getenv("LLM_FALLBACK_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
                "model": model}
    return {"base": (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
            "key": os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini")}


def configured() -> bool:
    return bool(_cfg()["key"])


async def _stream_one(cfg: dict, messages: List[dict], tools: Optional[List[dict]]) -> AsyncIterator[dict]:
    body: Dict = {"model": cfg["model"], "messages": messages, "stream": True, "temperature": 0.4, "max_tokens": 300}
    if tools:
        body["tools"] = tools
    calls: Dict[int, dict] = {}
    t0 = time.perf_counter()
    first = True
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=6.0), transport=http_util._transport_override) as c:
        async with c.stream("POST", cfg["base"] + "/chat/completions", json=body,
                            headers={"Authorization": f"Bearer {cfg['key']}"}) as r:
            if r.status_code != 200:
                raise RuntimeError(f"LLM HTTP {r.status_code}: {(await r.aread())[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {})
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if first and (delta.get("content") or delta.get("tool_calls")):
                    first = False
                    yield {"type": "ttft", "ms": (time.perf_counter() - t0) * 1000, "model": cfg["model"]}
                if delta.get("content"):
                    yield {"type": "text", "text": delta["content"]}
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
    if calls:
        yield {"type": "tool_calls", "calls": [calls[i] for i in sorted(calls)]}


async def stream_chat(messages: List[dict], tools: Optional[List[dict]] = None) -> AsyncIterator[dict]:
    """Yield {'type': 'ttft'|'text'|'tool_calls'}. Falls back to the secondary model if the primary fails
    before producing any output."""
    emitted = False
    primary = _cfg()
    try:
        async for ev in _stream_one(primary, messages, tools):
            emitted = True
            yield ev
        return
    except Exception as e:
        logger.warning("primary LLM failed (%s: %s)", type(e).__name__, e)
        if emitted:
            raise
    fb = _cfg("fallback")
    if fb is None:
        raise RuntimeError("LLM unavailable and no LLM_FALLBACK_MODEL configured")
    async for ev in _stream_one(fb, messages, tools):
        yield ev
