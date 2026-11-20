# Demo script (3 minutes) and 2-minute video shot list

**Setup:** patient app on the left (`/?demo=1`, action timeline open), nurse console `/console/` on the right. Use **wired earphones with a mic**: venue noise ruins ASR. Press **Reset demo data** in the demo drawer right before each run (it seeds *Lakshmi, 62, Jayanagar*). Have the WhatsApp sandbox joined on your phone (optional; the inbox shows the same message). Test the phone hotspot at 8:45.

| Time | Moment | You say | What judges see and hear |
| --- | --- | --- | --- |
| 0:00 | Hook | (pitch line 1) | Pre-call screen, one big button |
| 0:15 | **1. Initiate + Understand** | "Namaste. Mere ghutne mein bahut dard hai, chalne mein problem ho rahi hai. Jayanagar ke paas koi doctor?" | Falcon answers with a short filler, then the result. Timeline: `triage_symptoms` then `search_doctors` (orthopaedics, routine) |
| 0:45 | **2. Assist** | "Kal subah ka time milega? Aur doctor Kannada ya Hindi bolte ho to better." | Doctor cards with language chips (green = matches you), distance, fee, PM-JAY. Agent recommends one and says why. The "Kannada ya Hindi" doctor request does **not** trigger a language switch |
| 1:10 | **3. Execute + conflict** | Before speaking: demo drawer, **Force slot conflict**. Then: "Haan, 10 baje wala book kar do." | `hold_slot` shows **CONFLICT** (red). Agent: the slot just went, 10:30 or 11? You: "10:30". `confirm_booking` succeeds, **appointment card + QR** appears |
| 1:35 | **4. Confirm + Follow up** | (none) | Spoken confirmation. Inbox drawer: message to patient and caregiver, **Murf voice note** player, `.ics`. WhatsApp lands on your phone if Twilio is set |
| 1:55 | **5. Hot-swap** | "Kannada dalli maathadi." (or tap the ಕನ್ನಡ pill) | Timeline: language swap card with the measured ms. Same voice, now Kannada, with a **recap of the booking in Kannada** (memory survived) |
| 2:20 | **6. After: proactive call** | Demo drawer: **Fast-forward to reminder call** | The app **rings**. Accept: the agent speaks first (reminder, "bring your old X-ray"). Fast-forward again, accept, say "paanch": rating logged on the console |
| 2:40 | **7. Safety** (if time) | "Seene mein dard ho raha hai." | Red banner, 108 guidance, console alert. Nurse types on the console and **the agent speaks the nurse's words** |
| 2:55 | Close | (pitch close) | |

**If anything fails live:** say "let me show you the recorded run" and play the backup video from the matching timestamp. Never debug on stage.

## 60-second pitch

> "Most Indians don't book doctors on apps. They call someone who speaks their language, and too often there's no one to call. **ArogyaVaani** is that someone. You talk the way you talk, in Hinglish, Kannada or Hindi. It finds the right specialist who *speaks your language*, books a real slot, and confirms on WhatsApp with a voice note for people who can't read. Then it calls *you* back with a reminder and asks how the visit went.
>
> Under the hood: Agora Conversational AI runs the real-time pipeline with Sarvam ASR for Indic speech. Our own LLM endpoint runs a multi-step tool loop with memory and RAG. Murf Falcon speaks every language in one consistent voice, and I used Gaurav's tip from the Falcon talk: `<ONE TIP YOU APPLIED>`. Agora's speak API lets a nurse take over the agent's voice when something is urgent. It runs on AWS.
>
> It's built for clinic chains and state health programs today, and the same agent re-skins to labs, pharmacies and insurance tomorrow. Thank you to Agora, Murf, AWS, KNOTiC and Polaris."

## Answers to have ready

| Question | Answer |
| --- | --- |
| Who pays, how big? | Clinic chains and state health programs pay per booked visit; same agent re-skins to labs, pharmacies, insurance claims. Every call is ConvoAI minutes. |
| Why a custom LLM, not Agora's built-in? | A stateful multi-round tool loop, RAG, memory, and a safety gate that runs before the model. |
| How do you switch language if TTS can't be updated live? | The update API only covers token and LLM fields, so we hot-swap: leave, then re-join with the new ASR and TTS locale; memory lives on our server. |
| Why this voice? English drug names inside Kannada? | One multi-native Falcon voice across 3 locales keeps the persona constant; English medical terms stay in Latin script and Falcon code-mixes them; the voice note adds a pronunciation dictionary. |
| Two people grab the same slot? Timeout mid-booking? | 120 s hold with TTL, confirm with an idempotency key; on conflict the agent offers the next two slots; a timeout retries once, then promises a callback. Every call is logged with latency. |
| Medical liability? | No diagnosis, deterministic red-flag list before the LLM, human escalation with nurse takeover. |
| Scale? | The LLM endpoint is stateless; the agent runs in Agora cloud per session; SQLite swaps for Postgres/DynamoDB; APScheduler for EventBridge. |

## 2-minute video shot list (record at 11:15, never later)

1. **0:00-0:10** Title card and one line on the problem.
2. **0:10-1:20** The full Hindi journey with the timeline visible: triage, search, conflict, booking, inbox/WhatsApp.
3. **1:20-1:40** Hot-swap to Kannada with the recap.
4. **1:40-1:55** Fast-forward, the reminder call, a voice rating.
5. **1:55-2:00** Architecture slide (Agora, Murf, AWS as text) plus the repo URL.

Record with OBS (system audio + mic). Burn in **English captions** for every Hindi and Kannada line; many mentors do not speak them.
