# ArogyaVaani backend (FastAPI)

One process serves everything on `:8000`:

| Path | What |
| --- | --- |
| `/llm/chat/completions` | OpenAI-compatible SSE endpoint Agora ConvoAI calls: tool loop, memory, safety gate (`src/llm.py`) |
| `/clinic/v1/*` | Mock external Clinic Booking API: slots, 120 s holds, idempotent bookings, 409 on conflict (`src/clinic_api.py`) |
| `/get_config`, `/session/*`, `/call/accept`, `/startAgent`, `/stopAgent` | Token minting and agent lifecycle for the web app (also under `/api/*`) |
| `/console/*`, `/session/{id}/speak` | Nurse console data and the Agora `speak` takeover (header `X-Console-Password`) |
| `/demo/*` | Demo controls (force conflict, fast-forward reminder, reset, seed); disabled with `DEMO_MODE=0` |
| `/ws/events/{channel}` | Live tool/UI events; `patient:<id>` carries proactive `incoming_call` events |
| `/healthz`, `/metrics` | Health checks (db, keys) and p50 turn latency |
| `/`, `/static/*` | Built web app (when `web/out` exists) and generated voice notes / `.ics` files |

## Layout

```
src/server.py          routes + lifespan          src/agent_session.py  Agora lifecycle, language profiles, hot-swap, speak
src/llm.py             brain: SSE tool loop       src/llm_client.py     provider adapter, streaming tool calls, failover
src/tools/registry.py  typed tool registry        src/tools/handlers.py the 16 tools
src/triage.py          red flags + specialty      src/kb.py             BM25 RAG over data/kb/*.md
src/clinic_api.py      booking API                src/notify.py         messages, .ics, Murf voice note, Twilio
src/scheduler.py       reminder/feedback jobs     src/db.py             SQLModel tables
src/i18n.py            hi/kn/en strings, spoken times, voice language-switch detection
data/doctors.json      25 FICTIONAL doctors       scripts/murf_voices.py, murf_say.py, gen_doctors.py
```

## Run and test

```bash
bun run setup && cp .env.example .env.local   # from the repo root, then fill the keys
bun run dev                                   # backend + web
bun run test                                  # 104 tests, no keys or network needed
```

See `.env.example` for every variable. Never put `PORT` in `.env.local` for tests; the suite sets its own env.
