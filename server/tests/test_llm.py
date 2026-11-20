"""The brain: SSE contract, tool loop with filler, red-flag gate, escalation hold, sentence cap."""
import json

import pytest
from fastapi.testclient import TestClient

import db
import i18n
import llm
import llm_client
from events import hub
from tests.conftest import next_weekday_date

KEY = {"Authorization": "Bearer test-key"}


def sysmsg(session="s1", lang="hi-IN", patient="p1"):
    return {"role": "system", "content": f"session={session};lang={lang};patient={patient}"}


def script(*rounds):
    """Fake provider: each call to stream_chat plays the next scripted round."""
    it = iter(rounds)
    calls = []

    async def fake(messages, tools=None):
        calls.append(messages)
        try:
            rnd = next(it)
        except StopIteration:
            rnd = [{"type": "text", "text": "ok."}]
        yield {"type": "ttft", "ms": 5.0}
        for ev in rnd:
            yield ev

    fake.calls = calls
    return fake


def tc(name, args, id="c1"):
    return {"type": "tool_calls", "calls": [{"id": id, "name": name, "arguments": json.dumps(args)}]}


def parse_sse(body: str):
    out = []
    for line in body.split("\n\n"):
        if line.startswith("data: "):
            out.append(line[6:])
    return out


def post(body, headers=KEY):
    return TestClient(llm.app).post("/chat/completions", json=body, headers=headers)


def spoken(body: str) -> str:
    text = ""
    for d in parse_sse(body):
        if d != "[DONE]":
            text += json.loads(d)["choices"][0]["delta"].get("content", "") or ""
    return text


def test_health():
    assert TestClient(llm.app).get("/health").json()["status"] == "ok"


def test_auth_and_validation():
    body = {"messages": [sysmsg(), {"role": "user", "content": "hi"}], "stream": True}
    assert post(body, headers={}).status_code == 401
    assert post(body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert post({"messages": [], "stream": True}).status_code == 400
    assert post({**body, "stream": False}).status_code == 400


def test_sse_contract(monkeypatch):
    monkeypatch.setattr(llm_client, "stream_chat", script([{"type": "text", "text": "नमस्ते। बताइए।"}]))
    r = post({"messages": [sysmsg(), {"role": "user", "content": "namaste"}], "stream": True})
    assert "text/event-stream" in r.headers["content-type"]
    chunks = parse_sse(r.text)
    assert chunks[-1] == "[DONE]"
    first = json.loads(chunks[0])
    assert first["object"] == "chat.completion.chunk" and first["choices"][0]["delta"]["role"] == "assistant"
    assert json.loads(chunks[-2])["choices"][0]["finish_reason"] == "stop"
    assert "नमस्ते" in spoken(r.text)


def test_tool_loop_streams_filler_then_answer_and_emits_events(monkeypatch):
    fake = script([tc("triage_symptoms", {"symptoms": "ghutne mein dard"})],
                  [{"type": "text", "text": "आपको orthopaedics doctor दिखाना चाहिए।"}])
    monkeypatch.setattr(llm_client, "stream_chat", fake)
    r = post({"messages": [sysmsg(), {"role": "user", "content": "mere ghutne mein dard hai"}], "stream": True})
    text = spoken(r.text)
    assert any(text.startswith(f) for f in i18n.FILLERS["hi-IN"]), text   # filler BEFORE the tool result
    assert "orthopaedics" in text
    types = [(e["type"], e.get("tool")) for e in hub.recent("s1")]
    assert ("tool_start", "triage_symptoms") in types and ("tool_end", "triage_symptoms") in types
    # tool result was fed back to the model as a tool message
    assert fake.calls[1][-1]["role"] == "tool" and "orthopaedics" in fake.calls[1][-1]["content"]
    assert db.get_call_session("s1").stage == "DURING"


def test_red_flag_gate_skips_llm_and_escalates(monkeypatch):
    fake = script([{"type": "text", "text": "should never be spoken"}])
    monkeypatch.setattr(llm_client, "stream_chat", fake)
    r = post({"messages": [sysmsg(), {"role": "user", "content": "seene mein dard ho raha hai"}], "stream": True})
    assert "108" in spoken(r.text) and not fake.calls
    assert db.get_call_session("s1").escalated
    assert any(e["type"] == "red_flag" for e in hub.recent("s1"))


def test_open_escalation_replies_only_with_holding_line(monkeypatch):
    fake = script([{"type": "text", "text": "booking now"}])
    monkeypatch.setattr(llm_client, "stream_chat", fake)
    db.update_call_session("s1", escalated=True)
    r = post({"messages": [sysmsg(), {"role": "user", "content": "kal ka appointment chahiye"}], "stream": True})
    assert spoken(r.text) == i18n.HOLDING["hi-IN"] and not fake.calls


def test_kannada_filler_and_script(monkeypatch):
    monkeypatch.setattr(llm_client, "stream_chat", script([tc("get_patient_profile", {})], [{"type": "text", "text": "ನಮಸ್ಕಾರ."}]))
    r = post({"messages": [sysmsg(lang="kn-IN"), {"role": "user", "content": "ನಮಸ್ಕಾರ"}], "stream": True})
    assert any(spoken(r.text).startswith(f) for f in i18n.FILLERS["kn-IN"])


def test_tool_rounds_are_bounded(monkeypatch):
    rounds = [[tc("get_patient_profile", {}, id=f"c{i}")] for i in range(20)]
    fake = script(*rounds)
    monkeypatch.setattr(llm_client, "stream_chat", fake)
    r = post({"messages": [sysmsg(), {"role": "user", "content": "hello"}], "stream": True})
    assert r.status_code == 200 and len(fake.calls) <= llm.MAX_TOOL_ROUNDS + 1
    # last round must not offer tools, so the model is forced to answer
    assert parse_sse(r.text)[-1] == "[DONE]"


def test_provider_failure_speaks_failure_message(monkeypatch):
    async def boom(messages, tools=None):
        raise RuntimeError("down")
        yield  # pragma: no cover
    monkeypatch.setattr(llm_client, "stream_chat", boom)
    r = post({"messages": [sysmsg(), {"role": "user", "content": "hello"}], "stream": True})
    assert spoken(r.text) == i18n.FAILURE["hi-IN"] and parse_sse(r.text)[-1] == "[DONE]"


def test_set_language_schedules_swap_after_reply(monkeypatch):
    swapped = []

    async def hook(sid, lang):
        swapped.append((sid, lang))
    monkeypatch.setattr(llm, "SWAP_DELAY_S", 0)
    from tools import handlers
    monkeypatch.setitem(handlers.HOOKS, "request_swap", hook)
    monkeypatch.setattr(llm_client, "stream_chat",
                        script([tc("set_language", {"language": "kn-IN"})], [{"type": "text", "text": "ಸರಿ."}]))
    import asyncio

    async def run():
        out = ""
        async for piece in llm.agent_turn("s1", "hi-IN", "p1", [{"role": "user", "content": "Kannada dalli maathadi"}]):
            out += piece
        await asyncio.sleep(0.05)
        return out
    asyncio.run(run())
    assert swapped == [("s1", "kn-IN")]


def test_sentence_cap_and_abbreviations():
    c = llm.SentenceCap(2)
    out = "".join(c.feed(x) for x in ["Dr. Rao is at 10.30 today. ", "Fee is 600 rupees. ", "Third sentence. "])
    assert out.count("Dr. Rao") == 1 and "Third" not in out and "Fee is 600" in out
    c2 = llm.SentenceCap(2)
    assert "**" not in c2.feed("**Hello** [x] world")


def test_parse_session_info():
    info = llm.parse_session_info([sysmsg("abc", "kn-IN", "p9"), {"role": "user", "content": "x"}])
    assert info == {"session": "abc", "lang": "kn-IN", "patient": "p9"}


def test_system_prompt_includes_context():
    db.upsert_patient("p1", name="Lakshmi", area="Jayanagar", languages="kn,hi")
    p = llm.build_system_prompt("p1", "s1", "kn-IN")
    assert "Kannada" in p and "Lakshmi" in p and "IST" in p and "{{" not in p


@pytest.mark.parametrize("text,expect", [
    ("Kannada dalli maathadi", "kn-IN"),
    ("kannada mein baat karo", "kn-IN"),
    ("ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಿ", "kn-IN"),
    ("Hindi mein baat karo please", "hi-IN"),
    ("हिंदी में बात करो", "hi-IN"),
    ("please speak english", "en-IN"),
    ("doctor Kannada ya Hindi bolte ho to better", None),      # doctor preference, not a switch
    ("Kannada bolne wale doctor chahiye", None),
    ("mujhe ghutne mein dard hai", None),
    ("Hindi ya Kannada mein baat karo", None),                   # ambiguous: leave it to the LLM
])
def test_detect_language_request(text, expect):
    assert i18n.detect_language_request(text) == expect


def test_voice_switch_bypasses_llm_and_queues_swap(monkeypatch):
    fake = script([{"type": "text", "text": "never"}])
    monkeypatch.setattr(llm_client, "stream_chat", fake)
    from tools import handlers
    r = post({"messages": [sysmsg(lang="hi-IN"), {"role": "user", "content": "Kannada dalli maathadi"}], "stream": True})
    assert spoken(r.text) == i18n.SWITCH_ACK["kn-IN"] and not fake.calls
    assert any(e["type"] == "tool_end" and e["tool"] == "set_language" for e in hub.recent("s1"))
