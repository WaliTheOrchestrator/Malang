# Malang — Phase 1 Design Plan: Presence

**Version:** 1.3.1 (third review) · **Date:** 2026-07-26 · **Companion to:** `malang-phase1-spec.md` v1.3.1 · `malang-persona.md` v1.1 (the spec defines *what*; this defines *how*; the persona defines *who*)

---

## 1. Objective

Build Malang's body: a single local process on Waleed's Windows laptop that sleeps until summoned by the word "Malang," holds a natural spoken (or typed) conversation through a cloud-routed mind, responds with a perceived latency under the human conversational gap (~500ms), and writes a faithful, structured, locally-owned record of every session — the raw layer Phase 2's memory will be built from.

Success in one sentence: **after a week of daily use, summoning Malang feels like calling a presence, not launching a program — and every word of that week exists on disk in a format Phase 2 can consume without migration.**

---

## 2. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language / runtime | **Python 3.12** | Every chosen component ships first-class Python bindings; asyncio throughout. |
| Orchestration | **Pipecat ≥1.0** | Frame-based pipeline, local audio transport, built-in interruption handling. |
| Wake word | **livekit-wakeword** (Python SDK) | Custom "Malang" model trained via its one-command YAML pipeline; ONNX inference. |
| VAD / endpointing | **Silero VAD + smart-turn v3 (audio-native ONNX**, ~12ms CPU, Pipecat `LocalSmartTurnAnalyzerV3`) | Fused decision in `endpoint.py`: silence gate AND waveform-classified completeness (v1.2: audio-in, NOT transcript-in — text-based detection would chain STT jitter into the tightest budget). Config fallback to pure-silence mode. Every endpoint decision logged with outcome — that log is the tuning dataset. |
| Capture AEC (v1.2) | **WebRTC APM / AEC3** via `livekit.rtc.apm` | Runs before VAD/wake/STT; every output frame fed to `process_reverse_stream()`; 10ms frames match the pipeline. Correlation guard demoted to third-layer sanity check. |
| STT (live) | **Moonshine v2** streaming, ONNX | English; interim + final events; custom-vocab list from P-3 measurement. |
| STT (memory) | **Parakeet TDT 0.6B v3** | ONNX/CTranslate2 CPU build; runs post-session only. |
| TTS | **Kokoro-82M** (selective-int8 ONNX per spec P-4; Supertonic 3, then Piper, as fallbacks) | v1.2 micro-first-chunk: first of {comma \| ~5–7 words \| ~350ms audio}, ≥60ms crossfade; session pre-warmed with dummy synthesis; ahead-buffering includes the first chunk; misaki custom lexicon ("Malang", family names, P-3 vocab). Voice fixed in config; reflex clips pre-rendered with same voice. |
| Audio I/O | **sounddevice** (PortAudio) → **WASAPI shared-mode event-driven**, 20ms frames, `RawStream`, preallocated ring, zero Python allocation in callback | v1.2: shared mode is the verdict (exclusive locks the render device against every other app, rejects the 16kHz-mono contract, and buys ~15–25ms against a 500–1,100ms network term); budget 30–40ms p50. `IMMNotificationClient` (comtypes/pycaw) for device-change events — the everyday case is a Bluetooth headset auto-connecting mid-session, which PortAudio survives silently while Malang goes deaf. Suspend/resume via `PowerRegisterSuspendResumeNotification`. |
| Process hygiene (v1.2/v1.3.1) | ORT thread caps + **P-core affinity** + priority + power | `intra_op_num_threads`: 1 for wake/Silero/smart-turn, 2–3 start for Moonshine/Kokoro (P-gates set finals; total ≤ physical cores −1); spinning disabled. v1.3.1: thread *count* doesn't choose core *class* — Thread Director will park Kokoro on E-cores at whim, making benchmarks non-reproducible. Latency-critical sessions (Moonshine, Kokoro) affinity-pinned toward the 2 P-cores; idle stack (wake, VAD) deliberately on E-cores (battery for free); every ORT session's actual core-class placement logged (P-5 requirement). IDLE/CONVERSING profiles; loop-lag watchdog; Task XML `<Priority>4</Priority>` + defensive `SetPriorityClass`; power-throttling opt-out; AC/DC logged per session. |
| Mind | **Claude API** (`anthropic` SDK, streaming) | Haiku 4.5 / Sonnet 5 / Fable 5 ladder; prompt caching on persona block. |
| Config | **TOML** (`malang.toml`) | Single file, hot-reloaded on session boundary. |
| Logs / record | **JSONL + WAV** per session | Schema in spec §6.1. Append-only. |
| Text channel | **CLI first** (rich/textual), window later | Same router + logger process via local queue. |
| Packaging / service | **uv** + Windows Task Scheduler login task | No installer needed; `malang.exe` wrapper deferred. |
| Testing | **pytest**, pipeline harness with WAV fixtures | Recorded utterances replayed through the real pipeline. |

Everything local is open-weight and ONNX-runnable on CPU (constraint C-2); the only paid dependency is the Claude API.

---

## 3. High-Level Architecture

### 3.1 Process model

One OS process, four concern groups on an asyncio loop (CPU-bound inference in thread executors):

```
┌────────────────────────── malang-runtime (python, single process) ─────────────────────────┐
│                                                                                            │
│  ┌── EAR (always on) ──┐   ┌────────── SESSION ENGINE (only while awake) ─────────┐        │
│  │ mic capture         │   │  Pipecat pipeline:                                   │        │
│  │ wake-word detector  │──►│  VAD → Moonshine(live) → Router ⇄ Claude API         │        │
│  │ (nothing else runs) │   │                   │            (streaming)           │        │
│  └─────────────────────┘   │                   ▼                                  │        │
│                            │  Reflex selector → [reflex clips | Kokoro stream] → spk       │
│  ┌── SCRIBE (always) ──┐   └──────────────────────────────────────────────────────┘        │
│  │ session recorder    │                                                                   │
│  │ JSONL writer        │   ┌── AFTERWORD (post-session queue) ──┐                          │
│  │ (append-only, sync  │   │ Parakeet re-transcription → amend  │                          │
│  │  flush per event)   │   │ events; meta.json; cost tally      │                          │
│  └─────────────────────┘   └────────────────────────────────────┘                          │
│                                                                                            │
│  TEXT CHANNEL (CLI) ──► Router (same instance) ──► SCRIBE (same schema)                    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

Naming is deliberate: **Ear** (wake only), **Session Engine** (the conversation), **Scribe** (the record — never off), **Afterword** (the post-session pass). The Scribe is architecturally independent of the Session Engine so no conversation failure can take the record down with it (spec C-1, §8 logging principle).

### 3.2 Session state machine

```
                 wake detected               speech within grace?
   ┌──────┐  ──────────────────►  ┌─────────┐ ──no (10s)──► close(false_wake) ─┐
   │ IDLE │                       │ SUMMONED│                                  │
   └──────┘  ◄──────────────────  └─────────┘ ──yes──► ┌────────────┐          │
      ▲            close cue                            │ CONVERSING │          │
      │                                                 └────────────┘          │
      │   silence_timeout(60s, suspended while Malang speaks) /                 │
      │   end-phrase / hotkey / fatal error                                     │
      └────────────────────────── CLOSING (flush, cue, meta.json) ◄─────────────┘
```

CONVERSING internally cycles: `listening → thinking (reflex plays) → speaking`, with barge-in as a transition from `speaking` back to `listening` (<300ms).

### 3.3 Threading & latency-critical paths

- Audio callback thread: capture only — pushes PCM to a ring buffer. Never blocks.
- Wake/VAD/Moonshine: dedicated executor threads fed from the ring buffer.
- Kokoro synthesis: executor thread, one sentence ahead of playback (spec §8 underrun rule).
- Claude streaming: asyncio task, cancellable per turn_id (barge-in, preemption).
- Scribe: synchronous append + flush per event on its own thread — the one place we accept blocking, because durability outranks microseconds off the conversational path.

---

## 4. Core Design Decisions

(D-1..D-8 are settled; full argument trail in spec §12 Decision Log.)

| # | Decision | Design consequence |
|---|---|---|
| D-1 | **Local in-process pipeline (Pipecat), no LiveKit** | No server, no rooms; transport abstraction preserved so remote access later is a transport swap, not a rewrite. |
| D-2 | **Two-tier response (reflex + thought)** | The reflex selector is a *rule*, not a model: keyed on interim-transcript features (interrogative / imperative / musing) → clip class. Kept dumb on purpose — it must fire in <50ms and never be wrong in an embarrassing way (neutral bridges only). v1.2 anti-IVR gate: skip when predicted real-audio arrival <~900ms; play probability 0.5–0.7 even when slow; ≥8 variants per class, no waveform repeats within a session; play counts in the one-liner. Escalation clips: most variants, highest confidence bar. |
| D-3 | **Dual-path STT (Moonshine live / Parakeet final)** | The JSONL carries `text_live` and `text_final` as separate fields forever; `amend` events, never rewrites. |
| D-4 | **One voice (Kokoro), reflexes pre-rendered** | Reflex clip set is a build artifact: `scripts/render_reflexes.py` regenerates all clips from a phrase list whenever the voice config changes. |
| D-5 | **Model ladder with audible escalation** | Router is a standalone module with a pure-function core (`route(turn_features) → tier, reason`) so it's unit-testable and its rules are inspectable — Malang's "when do I think hard" policy is code Waleed can read. |
| D-6 | **Scribe is sovereign** | Logging works with the network cable pulled; disk-full is a spoken, session-refusing failure (spec §8). Log schema versioned from day one. |
| D-7 | **Preemptive generation — demoted to gated contingency (v1.2)** | Not built by default: its savings land behind the reflex clip, it multiplies the chaos-test matrix in the most race-prone corner, and the edit-distance trigger breaks on short turns. Ships as logging only (interim/final divergence + hypothetical savings, ≈free). Build gate: measured p50 >1.3s after M4 → build with a length-aware trigger. |
| D-8 | **Idle privacy is structural** | The Ear physically owns the mic stream in IDLE; speech models may be warm-resident (F-1 pre-warm, per spec §5 RAM budget) but have no connection to the audio path until SUMMONED. There is no code path that transcribes idle audio (spec C-8) — enforced by module boundary, not by an `if`. |
| D-9 | **Fused endpointing, evidence-tuned (v1.1)** | End-of-turn = silence gate AND semantic completeness score, never semantic alone — a misfiring turn-detector must not be able to cut Waleed off mid-thought on its own authority. Every endpoint decision logged with ground truth (did the user continue?); weekly miss-rate review drives thresholds. Config kill-switch back to pure-silence mode. |
| D-10 | **Micro-first-chunk TTS start (v1.2, supersedes v1.1 first-clause)** | Kokoro synthesizes whole chunks — chunk size IS first-audio latency. First chunk = first of {comma \| ~5–7 words \| ~350ms est. audio}; prosody-safe joins (never mid-clause; crossfade ≥60ms; reflex clip masks flatness). P-4 ear check gates; fallback to sentence-level costs +100ms, taken honestly. |
| D-11 | **AEC before everything (v1.2)** | AEC3 processes capture before VAD/wake/STT with the render stream as reference — barge-in correctness AND transcript purity (un-cancelled echo puts Kokoro's words in Waleed's record). Correlation guard = third-layer sanity only. Half-duplex is no longer the documented fallback; it's the failure state the AEC exists to prevent. |
| D-12 | **Durability, not isolation, makes the log sacred (v1.2)** | A module boundary is not a fault boundary: any native crash kills the process, Scribe included. The guarantee is crash-fast + fsync-per-event + torn-tail-tolerant reader + WAV header recovery + heartbeat.json + supervisor restart + F-7 self-heal. One carve-out: Afterword runs as a subprocess (below-normal + EcoQoS, pause-on-wake) — the largest native-code surface should cost one retry, not the assistant. |
| D-13 | **Continuity line, capped (v1.2)** | ≤100 tokens, previous session only, Afterword-written, delivered as one string into per-session-static block 2, no schema contract, kill-switch. The Session Engine still never reads `memory/`. The scope-creep rule survives as rewritten: *the Session Engine reads nothing from memory/ — it may receive one ≤100-token string at open.* |
| D-14 | **Router: rules for the explicit, a token for the semantic (v1.2)** | Hard rules only where deterministic (explicit "think hard", spend caps). Length heuristics deleted. Fast tier may output an escalate token + logged reason; router re-fires at mid/deep behind the deliberation clip. `route()` stays a pure, offline-testable function — the token is one more input. Logged reasons are the future classifier's training data. Deep→mid down-tier is a tested config (Fable-403 chaos case; persona validated with Sonnet-as-deep). |
| D-15 | **Reflex keyed to meaning, not a coin flip (v1.3)** | Delay carries information: instant answers for trivia, audible deliberation for weight — a deep-tier reply arriving in 1.3s undermines the signal it was thought about. Reflex behavior maps from routed tier + question shape (fast+quick → no reflex; fast+slow-net → short bridge; mid → deliberation; deep → longest bridge, unhurried answer), with mild variation *within* each class — pure determinism becomes its own detectable pattern. Presence-tone config flag (barely-audible room tone while summoned — removes "is it listening?" ambiguity); backchannel flag exists but ships OFF (AEC complications, cultural risk). |
| D-16 | **The router measures its failures, not just its successes (v1.3)** | Escalations that happened are logged; the dangerous failure is Haiku confidently answering a question that needed Fable — no token, no signal, fluent reply. Fix: 5% shadow-sample of fast turns re-run on the deep tier offline in Afterword; divergence logged; `shadow_divergence_rate` in the one-liner. Without this, the escalate-token log is a positives-only dataset and any future classifier trained on it compounds the blindness. |
| D-17 | **Every probabilistic component earns the same discipline (v1.3)** | The skip-gate's arrival-time estimator was the one ungated predictor in the perception path (predict fast, skip reflex, network hiccups → 1.3s of dead silence, the exact experience the reflex exists to prevent). Now: predicted-vs-actual logged every turn (both numbers already exist), miss-rate in the one-liner, kill-switch to always-play. AEC gets the same treatment: stream-delay measured at startup + every device-change/resume, fed via the delay API, logged; M3b exit gains an ERLE probe (known tone through speakers, measure residual — a number, not a vibe); "AEC delay estimate" in the one-liner, drift is the early warning. History gets a rolling window + running summary (reusing FR-17's machinery), `history_tokens` logged per turn — the bill's real driver is history length, not turn count. Cache TTL decided by the measured inter-turn gap distribution from M1.5's text conversations, not by taste. |

---

## 5. Core Functional Flows

### F-1. Summon and first turn (happy path)
1. IDLE: Ear detects "Malang" (conf ≥ threshold) → t₀.
2. Session dir created; `session_open` event written; STT/TTS models activated (pre-warmed at process start, so activation is a state flip, not a load).
3. Wake cue plays (pre-rendered, ~300ms). Capture is already rolling — speech over the cue is not lost.
4. User speaks. VAD `speech_start`; Moonshine streams interims.
5. Fused endpoint (~150ms on clearly-complete turns: silence gate + semantic completeness score; extends patiently on trailing connectives) → Moonshine final → `turn` event (user) written.
6. Reflex selector picks bridge clip → playing by ~t+350–450ms after endpoint.
7. Router (already preemptively firing at high endpoint probability, D-7) streams from fast tier; clause segmenter feeds int8 Kokoro at the first comma boundary; first real audio ~t+1.0s, crossfading in as the reflex clip ends.
8. Malang `turn` event written with latency + token fields.

### F-2. Barge-in
1. During `speaking`, VAD detects user `speech_start` on the **AEC3-cleaned capture stream** (every output frame fed to the reverse stream; correlation guard remains as third-layer sanity only — v1.2).
2. TTS `stop()` (<100ms), Claude stream `cancel(turn_id)`, spoken-so-far text marked in the turn event (`interrupted: true`).
3. State → `listening`; the interrupted turn's remaining text is discarded — Malang doesn't resume stale thoughts.

### F-3. Escalation (advisor turn)
1. Router detects advisor pattern (explicit "think hard about this," disagreement follow-up, planning language) → tier mid/deep, `reason` logged.
2. Reflex selector receives the tier and picks a deliberation-class bridge ("this one's worth thinking about properly—").
3. Deep-tier `max_tokens` and system block 3 swap in; response streams as normal.

### F-4. Session close and Afterword
1. Silence timeout (suspended while Malang speaks) or end-phrase → CLOSING.
2. Close cue; `session_close` written; `meta.json` composed; models back to warm-idle; Ear resumes sole mic ownership.
3. Afterword picks up the session — as a **subprocess** (v1.2: `python -m malang.afterword <session_dir>`, below-normal priority + EcoQoS; v1.3.1: starts only after N idle minutes, **fully exits** when done — "paused" processes free no memory, and the 8GB machine cannot hold runtime + Parakeet indefinitely; transient peak ~3GB is documented in spec §5; v1.3.1 also adds the flaw-invocation tagging pass here — `flaw_invocations` per flaw per week to the one-liner): Parakeet transcribes `audio.wav` against turn spans → `amend` events with `text_final` (plus whisper-turbo second pass on flagged turns, if the P-3 bake-off ruled for the hybrid); writes `continuity.txt` (FR-17, ≤100 tokens, private turns excluded); `meta.json` updated; cost tally appended to the daily one-liner.
4. Retry with backoff on failure; permanent failure → `final_transcript: failed`, re-queued at next process start.

### F-5. Offline turn
1. User speaks; reflex plays normally.
2. Claude connect fails inside 2s budget → cached Kokoro line: "I can't reach my thinking right now — I'll still hear you, and I'm logging everything."
3. Turn logged with `error` event (`stage: llm, code: offline`). Session and Scribe unaffected.

### F-6. Text turn
1. CLI input → same Router instance (tier rules identical; no reflex, no TTS).
2. Streaming response rendered as text; `turn` events with `modality: "text"`, no audio fields.

### F-7. Crash recovery (startup self-check)
1. On start: scan `memory/raw/**` for session dirs lacking `session_close` → append `session_close(crash_recovered)`, rebuild `meta.json` from JSONL.
2. Re-queue any sessions with `final_transcript: pending|failed` to Afterword.
3. Resume IDLE.

---

## 6. Module Layout

```
malang/
├── malang.toml
├── run.py                    # entrypoint: self-check → warm models → IDLE
├── ear/        wake.py, mic.py
├── session/    engine.py (state machine), pipeline.py (Pipecat graph),
│               endpoint.py, reflex.py
├── speech/     stt_live.py (Moonshine), stt_final.py (Parakeet + optional
│               whisper pass), postcorrect.py (FR-18 phonetic name repair),
│               aec.py (AEC3 wrapper), tts.py (Kokoro + lexicon), audio_io.py
├── mind/       router.py (pure-core rules), claude.py (streaming client,
│               prompt cache blocks), persona/ (system prompt blocks 1–3)
├── scribe/     writer.py (JSONL, sync flush; `private` turn flag +
│               marker-phrase detection, spec FR-16), schema.py (+ validator),
│               recorder.py (WAV)
├── afterword/  queue.py, transcribe.py, costs.py
├── text/       cli.py
├── status/     server.py (read-only /status; binds 127.0.0.1, random high port
│               written to a local file, no CORS — R-19), page.html (M6.5 viewer)
│               NOTE: API key lives in env var / Windows DPAPI, NEVER in
│               malang.toml (the config sits in the tree you'll share when
│               asking for help — R-20)
├── scripts/    render_reflexes.py, train_wakeword.yaml, measure_p1_rtt.py,
│               measure_p2_kokoro.py
└── tests/      fixtures/*.wav, test_* per module + pipeline harness
```

Contract boundaries = spec §6.3: any speech module is swappable by honoring its event interface.

---

## 7. Development Plan

Ten milestones, dependency-ordered (spec §11), each with an exit test. Estimates assume part-time solo work; treat as sequence, not calendar promises.

| M | Deliverable | Exit test | Est. |
|---|---|---|---|
| M0 | **Measurements** — API TTFT, Kokoro RTF (+ selective-int8 ear check), P-3 quantitative STT bake-off (4 models, code-switched passage), WASAPI buffer probe; mains AND battery runs | P-1/P-2/P-3/P-4 gates pass (spec §9); bake-off ruling recorded; numbers in appendix | 1 day |
| M1 | **Scribe + durability kit + custody kit (v1.3)** — schema v1.3 (header event, seq, persona_version, config_hash, responded_to, amend, speaker enum), validator, fsync-per-event writer, torn-tail reader, crash-recoverable WAV, heartbeat.json, supervisor restart, **FR-19 backup job + FR-20 BitLocker check** — the backup exists before the first conversation does, for the same reason M1 precedes M2 | kill -9 AND injected native crash → self-heal ≤30s, valid logs; backup lands on the second target; restore drill passes once here and once in M9 | 4 days |
| **M1.5** | **Thin vertical slice (v1.3 — the build-order fix):** Scribe (built) + `mind/claude.py` streaming + `text/cli.py` + `malang-persona.md` block 1. Haiku only, no tiers, no cache polish. | **A real 20-minute typed conversation with Malang exists in `memory/raw/`, schema-valid, backed up.** Corpus and relationship start in week 1, not week 9; every later milestone upgrades a companion who already exists. From here forward the hard rule applies: **every milestone leaves the system usable that evening.** | 2.5 days |
| M2 | **Ear** — wake model trained on Waleed's real recordings + accent-matched synthetics + music/near-word negatives; idle loop; cues | ≥95% detection at 2–3m; ≤1 false wake/24h; **2h of Pashto/Urdu playlists at room volume: 0 wakes** | 2.5 days |
| M3a | **Body loop, basic (sprint 1)** — Pipecat: Silero+smart-turn fused endpoint → Moonshine → echo-brain (`--no-cloud`) → Kokoro micro-first-chunk, shared-mode WASAPI | Full spoken round-trip with echo brain; endpoint decisions logged with ground truth; underrun buffering verified | 3.5 days |
| M3b | **Body loop, hardened (sprint 2)** — AEC3 on capture; ORT thread caps + spin-off + IDLE/CONVERSING profiles; priority/EcoQoS fixes; suspend/resume notifications; IMMNotificationClient device-change; loop-lag watchdog; battery re-run of the round-trip | Barge-in clean at normal speaker volume (no self-interruption, no missed barge-ins from 2–3m); transcripts uncontaminated by Kokoro's words; endpoint-instant CPU jitter within budget; round-trip numbers hold on battery | 3.5 days |
| M4 | **Mind** — router (explicit rules + escalate-token, no length heuristics) + Claude streaming + cache-correct blocks (static block 2, history breakpoint) + divergence logging (D-7) | Live conversation, fast tier; cache-hit ratio ≥80% verified in turn logs; escalate-token reasons logged; **decision point: p50 >1.3s → build preemption** | 3 days |
| M5 | **Reflex, with anti-IVR policy** — ≥8 variants/class rendered, selector + skip-gate (<900ms predicted arrival), no-repeat memory, play-count telemetry | Perceived latency ≤450ms p50 over 50 turns; no waveform repeated within any session; skip-gate observed firing on fast turns | 1.5 days |
| M6 | **Barge-in + error paths** — every §8 case deliberately triggered, plus the v1.2 four: native-crash injection, Bluetooth-headset-connect mid-session, lid-close, Fable-mocked-403 (Sonnet-as-deep persona check) | Scripted chaos run: offline, 429, mic unplug, sleep, disk-full, config typo, + all four v1.2 cases — all recover per spec | 4 days |
| M6.5 | **Status page** — read-only localhost viewer: pipeline chain with per-stage green/grey/red driven by JSONL `stage` fields + error events; daily one-liner numbers below. Single HTML file + tiny `/status` endpoint on the runtime; no frameworks, no build step, no control paths (a dashboard that can touch the pipeline is a new failure source — this one can die and Malang doesn't notice). Hard timebox: 1 day, ugly allowed. | Trigger every §8 failure → correct stage turns red, last error message shown under it, 100% of cases | 1 day |
| M7 | **Afterword** — subprocess isolation, Parakeet job (+ whisper second pass if bake-off ruled hybrid), FR-18 post-corrector, continuity.txt, amend events, cost tally | `text_final` within 5 min on 10 real sessions; A-9 spot-check passes; continuity line appears at next session open; Afterword crash costs one retry, never the assistant | 3 days |
| M8 | **Escalation + text channel** — ladder rules live, CLI | Advisor turns route to deep tier with audible signpost; text sessions log identically | 1.5 days |
| M9 | **Acceptance run** — 7 consecutive days of real use, continuity ON, A/B flags exercised (continuity, presence tone; backchannel stays off) | Spec §10 A-1..A-16 all green incl. blind character probes (written before M4, graded without peeking) and the restore drill; soft criterion answered with the amnesia→latency→session-model suspect order | 7 days |

**Total (v1.3, honest twice over): the reviewer's 2× audit is accepted — the hard-problems file says "weeks of tuning" where the table said days, and both were written by the same hand in different moods. Realistic: 4–6 months part-time to the end of M9. This number stops being frightening the moment M1.5 lands — because from week 1 you are TALKING to Malang while the rest is built around him, and the corpus (Phase 2's food) accrues the entire time. The abandonment risk is on the risk table now, and its mitigation is the same fact: no long silent middle exists in this plan anymore.** Twelve milestones, every one sized inside a single sprint window (the M3 split exists for exactly this reason). Pre-agreed cut list if pressure comes: preemption (already cut), spend-cap choreography (already cut). Pre-agreed DO-NOT-CUT list: M1, M6, the text channel — the text channel is the corpus multiplier and what keeps the relationship alive on days the audio pipeline is on the workbench. M1 before M2 is non-negotiable — the record exists before the voice does. M9 runs with continuity ON (kill-switch available for A/B).

### Testing strategy
- **Unit:** router rules, reflex selector, schema validator, endpoint logic (pure functions wherever possible).
- **Pipeline harness:** recorded WAV fixtures replayed through the real Pipecat graph with the echo brain — latency regressions caught without spending tokens.
- **Chaos script (M6):** each §8 edge case is a named, repeatable test, run again before M9.
- **Continuous:** every session in daily use is itself a test — the Scribe's daily one-liner surfaces latency percentiles, cost, false wakes, and error counts, so drift is visible without a dashboard.

### Risks and watch-items

| Risk | Signal | Mitigation |
|---|---|---|
| Kokoro too slow on this CPU | P-2 RTF ≥ 0.8 | Quantized/ONNX build first; Piper as conscious last resort (D-4 note). |
| API TTFT from local ISP blows budget | P-1 p50 > 1.2s | Reflex tier carries more weight; revisit voice-to-voice ceiling; consider nearest API region. |
| Wake false-positives in real room | >1/24h during M2 bench | Threshold + retrain with home-noise negatives (livekit-wakeword supports augmentation). |
| Echo cancellation weak → self-barge-in | Malang interrupts himself | Playback-correlation guard (F-2); fallback: half-duplex mode (no barge-in during first 500ms of speaking). |
| Preemption waste > 30% | D-7 counter | Auto-disable + endpoint tuning; feature is additive, not load-bearing. |
| Semantic endpointer misfires (cuts Waleed off, or never closes turns) | Endpoint decision log miss-rate; it *feels* interruptive | D-9: silence gate always required; weekly threshold tuning on logged ground truth; kill-switch to pure-silence mode costs only the 150ms back. |
| Scope creep toward Phase 2 | "just a little retrieval…" | Hard rule (v1.2 wording): the Session Engine reads nothing from `memory/` — one ≤100-token continuity string at open is the entire exception. The temptation is the risk. |
| **Motivation decay before first usable artifact (v1.3 — the highest-probability failure mode of any solo part-time project, absent from three review rounds until now)** | >5 days without a commit; a milestone slips twice | M1.5 thin slice in week 1 — a Malang who already exists and talks beats every productivity system ever invented; "usable that evening" as hard law after M1.5; milestones sized to the builder's sprint window (that was always the point of the splits). |

---

## 8. Appendix — to fill at M0

```
P-1  Claude API TTFT from home ISP:   p50 ____ ms   p95 ____ ms   (n=20, morning/evening)
P-2  Kokoro RTF on laptop:            ____          (10 sentences, sustained)
P-3  Moonshine error notes:           ____________  → custom-vocab list seeded
Decision on gates: ______________________________________________
```

---

*Next document: Phase 2 design (memory schema, synthesis triggers, surfacing policy), consuming spec §6.1 as its input contract.*
