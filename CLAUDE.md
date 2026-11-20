# ArogyaVaani: project memory
## Mission
Hackathon: Build with Agora, Bengaluru, 21 Nov 2026. Track 5 "Voice AI for Bharat", problem PS11
"Multilingual Healthcare Assistant". HARD DEADLINE: submission 12:30 IST today. Optimise for a
flawless 3-minute live demo plus a README a mentor understands in 2 minutes.

## Product
Voice-first agent. A user speaks Hinglish / Hindi / Kannada (code-mixed is normal). The agent:
BEFORE: loads or creates the patient profile (name, age, area, languages, caregiver phone).
DURING: triages symptoms to a specialty plus urgency (NEVER diagnoses), detects red flags,
  recommends 2-3 doctors ranked by language match, distance, fee, PM-JAY empanelment.
ACTION: check_availability, then hold_slot (120 s TTL), then a spoken yes, then confirm_booking (idempotency key).
  On a 409 conflict, offer the next 2 slots. On a timeout, retry once, then promise a callback.
CONFIRM/AFTER: speaks the confirmation in the user's language; sends WhatsApp/SMS plus a Murf voice note
  plus an .ics file to the patient and caregiver; schedules a reminder "call" where the agent speaks first,
  gives prep instructions, collects a 1-5 voice rating, and offers a follow-up booking.
SAFETY: red flags (chest pain, stroke signs FAST, breathing difficulty, heavy bleeding,
  suicidal talk, pregnancy bleeding, infant fever) stop booking: tell the user to call 108
  and escalate_to_human. A nurse console can speak through the agent via the Agora /speak API.

## Architecture (do not deviate without asking)
- Base: AgoraIO-Conversational-AI/recipe-agent-tool-calling (Next.js web + FastAPI server).
- Agora ConvoAI REST: POST https://api.agora.io/api/conversational-ai-agent/v2/projects/{appid}/join
  and /agents/{id}/leave, /agents/{id}/speak (text <= 512 bytes, priority INTERRUPT|APPEND|IGNORE).
- ASR: vendor "sarvam" with params.language hi-IN | kn-IN | en-IN | "unknown" (auto-detect).
  Fallback: vendor "ares" with language "en-IN,hi-IN".
- LLM: OUR endpoint POST /llm/chat/completions (OpenAI-compatible, SSE streaming). Agora cloud
  calls it, so it must be publicly reachable. It runs the tool loop internally; Agora sees only text.
- TTS: vendor "murf", params {api_key, base_url wss://in.api.murf.ai/v1/speech/stream-input,
  voiceId, locale, model "FALCON", rate, pitch, sample_rate 24000}. One voice that supports
  hi-IN + kn-IN + en-IN (verify with GET https://api.murf.ai/v1/speech/voices?model=FALCON).
  Use "locale"; multiNativeLocale is deprecated.
- The update API cannot change ASR or TTS, so a language switch = leave + re-join ("hot-swap"). Memory
  lives in our DB keyed by session_id / patient_id, so it survives.
- RTM enabled (advanced_features.enable_rtm=true, parameters.data_channel="rtm") for transcripts.
  Our own WebSocket /ws/events/{session_id} pushes tool events to the UI timeline.
- Storage: SQLite via SQLModel. Scheduler: APScheduler. Messaging: Twilio (optional, with fallback).
- Deploy: Docker on AWS (EC2 or App Runner) behind HTTPS; ngrok for local dev.

## Rules
- Before using any Agora or Murf field, verify it with the agora-docs / murf-docs MCP tools or the
  docs .md pages. Never invent API fields. If docs and this file disagree, docs win: tell me.
- Every external call: 8 s timeout, 1 retry, structured log line {tool, ms, ok}.
- All secrets via .env (never committed); provide .env.example.
- Voice UX: replies <= 2 short sentences, numbers spoken naturally, confirm before any booking,
  same language and script as the user (hi-IN: Devanagari, English medical words kept in Latin;
  kn-IN: Kannada script). Stream a filler sentence before any tool call.
- Every feature must be demoable and visible in the UI. Prefer a working mock over a broken real API,
  but keep a real-API code path behind an env flag.
- Write pytest tests for tools and the booking API. Keep `make test` green.
- Small commits with clear messages after each prompt's checks pass.
