# Commudle submission: paste-ready answers

Fill the `<…>` slots once you have them. Submit by **12:10**.

| # | Field | Answer |
| --- | --- | --- |
| 1 | Project name and description | **ArogyaVaani: health in your language.** A voice-first agent that turns a code-mixed conversation (Hinglish, Kannada, Hindi) into a booked, confirmed and followed-up doctor visit. It triages without diagnosing, matches doctors who speak the patient's language, books with slot holds, confirms on WhatsApp/SMS with a Murf voice note, and later calls the patient back for a reminder and feedback. It escalates red flags to a human nurse who can speak through the agent. |
| 2 | Selected problem statement | Track 5, Voice AI for Bharat: Speak Your Language. PS11, Multilingual Healthcare Assistant (Before / During / Action / After). |
| 3 | GitHub repo (public) | `<https://github.com/<you>/arogyavaani>` |
| 4 | Working prototype / demo link | `<https://<aws-host>/>` (add `?demo=1` for demo controls; nurse console at `/console/`) |
| 5 | Agora Conversational AI integration | Agents start through the ConvoAI REST `join` (official `agora-agents` SDK) with Sarvam ASR (hi-IN / kn-IN / en-IN), our OpenAI-compatible custom LLM endpoint, and Murf Falcon TTS. RTC (Web SDK) carries audio, RTM carries live transcripts and agent state. `speak` powers the nurse takeover. Language hot-swap uses `leave` then a re-join, because the update API cannot change ASR/TTS, and memory persists server-side. Interruption is on (VAD start-of-speech). The exact redacted join payload is in the README and `docs/join-payload.json`. Outbound PSTN is on the roadmap. |
| 6 | Murf Falcon integration | `vendor: murf`, `model: FALCON`, voice `<voiceId>` across hi-IN, kn-IN and en-IN so one persona speaks every language, through the India WebSocket endpoint. Elder mode lowers the rate by 10. Devanagari/Kannada text with English medical terms is spoken code-mixed. Murf's HTTP stream API also renders a voice-note summary of each booking (MP3, with a pronunciation dictionary) for low-literacy users. |
| 7 | Agentic workflows and actions | A typed registry of 16 tools: profile memory, triage plus red-flag check, doctor search, KB retrieval (BM25 RAG), availability, hold, confirm (idempotent), cancel, confirmation (WhatsApp/SMS + inbox + .ics), voice note, follow-up scheduling, feedback, language switch, human escalation. Multi-step loop of up to 6 tool rounds per turn with a spoken filler. Errors handled: slot conflict (409) leads to alternatives, timeout leads to retry then callback, red flag leads to 108 plus a nurse. 109 backend tests. |
| 8 | Demo video | `<YouTube/Drive link>`: 2 minutes, English captions. |
