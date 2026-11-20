"""Provider adapter: SSE parsing of text + fragmented tool-call deltas, and primary->secondary failover."""
import json

import httpx
import pytest

import http_util
import llm_client


def sse(*deltas):
    body = ""
    for d in deltas:
        body += "data: " + json.dumps({"choices": [{"index": 0, "delta": d}]}) + "\n\n"
    return body + "data: [DONE]\n\n"


async def collect(msgs=None):
    return [e async for e in llm_client.stream_chat(msgs or [{"role": "user", "content": "hi"}], [])]


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k1")
    monkeypatch.setenv("LLM_BASE_URL", "https://primary.test/v1")
    monkeypatch.setenv("LLM_MODEL", "m-primary")
    monkeypatch.delenv("LLM_FALLBACK_MODEL", raising=False)


async def test_text_stream_and_ttft():
    body = sse({"role": "assistant", "content": ""}, {"content": "नमस्ते "}, {"content": "जी।"})
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    http_util.set_transport(httpx.MockTransport(handler))
    evs = await collect()
    assert [e["type"] for e in evs] == ["ttft", "text", "text"]
    assert "".join(e["text"] for e in evs if e["type"] == "text") == "नमस्ते जी।"
    assert seen["auth"] == "Bearer k1" and seen["body"]["model"] == "m-primary" and seen["body"]["stream"] is True


async def test_fragmented_tool_call_arguments_are_reassembled():
    body = sse(
        {"tool_calls": [{"index": 0, "id": "call_a", "function": {"name": "triage_symptoms", "arguments": ""}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": '{"symptoms": "ghu'}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": 'tne"}'}}]},
        {"tool_calls": [{"index": 1, "id": "call_b", "function": {"name": "get_patient_profile", "arguments": "{}"}}]},
    )
    http_util.set_transport(httpx.MockTransport(lambda r: httpx.Response(200, text=body)))
    evs = await collect()
    calls = next(e for e in evs if e["type"] == "tool_calls")["calls"]
    assert [c["name"] for c in calls] == ["triage_symptoms", "get_patient_profile"]
    assert json.loads(calls[0]["arguments"]) == {"symptoms": "ghutne"} and calls[0]["id"] == "call_a"


async def test_failover_to_secondary_before_first_token(monkeypatch):
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "m-fallback")
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "https://fallback.test/v1")
    hits = []

    def handler(req):
        hits.append(str(req.url))
        if "primary" in str(req.url):
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, text=sse({"content": "ok."}))
    http_util.set_transport(httpx.MockTransport(handler))
    evs = await collect()
    assert any(e["type"] == "text" and e["text"] == "ok." for e in evs)
    assert hits == ["https://primary.test/v1/chat/completions", "https://fallback.test/v1/chat/completions"]


async def test_no_fallback_configured_raises():
    http_util.set_transport(httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(RuntimeError):
        await collect()


def test_configured_flag(monkeypatch):
    assert llm_client.configured()
    monkeypatch.delenv("LLM_API_KEY")
    assert not llm_client.configured()
