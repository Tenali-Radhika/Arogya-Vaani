# Architecture

See the Mermaid diagram and integration details in [README.md](./README.md). Summary of one voice turn:

```
Browser (Agora RTC mic) -> Agora ConvoAI: Sarvam ASR -> POST <CUSTOM_LLM_URL>   (Authorization: Bearer)
   our /llm endpoint: red-flag gate -> language-switch gate -> LLM + tool loop (<= 6 rounds) -> SSE text only
-> Agora ConvoAI: Murf Falcon TTS -> Browser
Side channels: RTM (transcripts, agent state) | our WebSocket /ws/events (tool timeline) | Agora REST speak (nurse)
```

- **Lifecycle:** `agent_session.py` starts/stops agents via the `agora-agents` SDK. A language change is `leave` + `join` (ASR/TTS cannot be updated on a live agent); state lives in SQLite keyed by session and patient.
- **Booking:** tools call `/clinic/v1` over HTTP. Holds (120 s TTL) and idempotent confirms run inside one lock and DB transaction; a second hold on a slot returns 409.
- **After:** APScheduler fires reminder (T-12h) and feedback (T+2h) jobs, which push an `incoming_call` event to `/ws/events/patient:<id>`. Accepting starts a new agent whose greeting is the reminder.
- **Safety:** deterministic red-flag matcher runs before the model; while an escalation is open the endpoint returns a holding line only and booking tools refuse.
- **Scale path:** the LLM endpoint is stateless; swap SQLite for Postgres/DynamoDB, APScheduler for EventBridge Scheduler, and run N replicas behind a load balancer (the in-process lock in `clinic_api.py` becomes a DB transaction/row lock).
