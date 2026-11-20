# Agent Development Guide

For coding agents working on **ArogyaVaani**, a voice-first multilingual healthcare agent built on Agora
Conversational AI and Murf Falcon. Read [CLAUDE.md](./CLAUDE.md) for the product brief and rules.

## System shape

- **`server/`**: FastAPI (:8000). `src/llm.py` is Agora's custom-LLM endpoint (tool loop, SSE); `src/agent_session.py` is the
  only module that calls Agora's REST API (join / leave / speak, language hot-swap); `src/tools/` holds the 16 typed tools;
  `src/clinic_api.py` is a mock external booking API that the tools call over HTTP.
- **`web/`**: Next.js 16 / React 19 patient app (`/`) and nurse console (`/console`). In dev the browser calls `/api/*`
  (Next rewrites to the backend). In production the app is exported statically (`STATIC_EXPORT=1`) and served by FastAPI.
- Auth: Token007 from `AGORA_APP_ID` + `AGORA_APP_CERTIFICATE`; Agora cloud calls `/llm` with `Authorization: Bearer CUSTOM_LLM_API_KEY`.

## Patterns

- `llm.py` and `tools/` must stay free of `agora_agent` imports (provider-agnostic); only `agent_session.py` and `server.py` use the SDK.
- Verify any Agora or Murf field against the vendor docs before using it. The docs win over this repo's notes.
- All outbound HTTP goes through `http_util.request` (8 s timeout, 1 retry, structured log). Tests inject transports with `http_util.set_transport`.
- `CUSTOM_LLM_URL` must be public https; never default it to localhost. Do not put `PORT` in `server/.env.example`.
- Tools never raise into the voice turn: `registry.run_tool` converts failures into `{ok: false, error}`.
- Replies are voice: at most 2 short sentences, same language and script as the user. Red flags are handled deterministically before the LLM.
- Source files containing Hindi/Kannada text: write them with the editor tool, not shell heredocs.

## Commands

```bash
bun run setup        # venv + web deps
bun run dev          # backend :8000 + web :3000
bun run test         # backend pytest (104 tests)
bun run verify       # web: doctor + API contract + production build
```

## Done criteria

1. `bun run test` passes; web-affecting changes also pass `bun run verify:web`.
2. If you change env vars or setup steps, update `README.md`, `server/README.md` and `server/.env.example` together.

## Git conventions

- Conventional Commits: `type: description` or `type(scope): description` (`feat`, `fix`, `chore`, `test`, `docs`), lowercase, present tense.
- No AI tool names in commit messages or PR descriptions. No `Co-Authored-By` trailers. No `--no-verify`. No git config changes.
- Branch names: `type/short-description`.
