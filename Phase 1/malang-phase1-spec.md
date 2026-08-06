# Malang — Phase 1 Specification: Presence

**Version:** 1.3.1 (third review — the seams round: cache minimums, RAM truth, P/E cores, P-5 reversal, blind grading, flaw telemetry) · **Date:** 2026-07-26 · **Status:** Decided (discussion closed, ready to build)
**Owner:** Waleed Khan · **Architect of record:** Fable 5
**v1.1 change:** four latency optimizations folded in (semantic endpointing, clause-level TTS start, int8 Kokoro, WASAPI event-driven output). Target voice-to-voice drops 1.4s → ~1.1s p50. No architectural changes.
**v1.2 change (expert-panel review, 2026-07-26):** accepted amendments from the four-reviewer adversarial panel — real AEC on the capture path; audio-native turn detection (smart-turn v3); durability additions (supervisor restart, heartbeat, native-crash chaos test); wake-word trained on Waleed's own voice + media negatives; Kokoro micro-first-chunk + selective int8 + name lexicon; prompt-cache block repair; reflex anti-IVR policy; router escalate-token (length heuristics deleted); preemptive generation demoted to measured contingency; P-3 becomes a quantitative STT bake-off; capped continuity line adopted; latency re-baselined honestly to ~1.3s p50 real / ≤450ms perceived. Rejected as over-engineering: stacked dual AEC, smart-turn fine-tuning, Whisper-as-default, Scribe process split, 80% spend-cap choreography. Architecture unchanged — the panel proposed no redesign.

---

## 1. Problem Statement

Waleed is building Malang, a personal AI system meant to reflect how he reasons — extended by knowledge he doesn't yet have — with all memory held in his own custody, on his own machine. Phase 1 is Malang's **presence**: the ability to be summoned by voice ("Malang"), hold a natural spoken conversation, and go silent again.

The problem Phase 1 solves is twofold:

1. **Presence must feel alive.** A voice loop that takes 2+ seconds per turn feels like a walkie-talkie, not a companion. On the available hardware (Windows laptop, no discrete GPU) with a cloud reasoning layer, the pipeline must reach human-conversational perceived latency (≤500ms to first audio) despite a real voice-to-voice floor around 1 second.

2. **Every conversation must be captured faithfully from day one**, even though the memory system (Phase 2) does not exist yet. The earliest conversations — where the relationship forms — are unrecoverable if not logged. Phase 1's logging format is a Phase 2 contract: it determines whether memory is built incrementally or via painful migration.

Explicitly **not** Phase 1's problem: memory retrieval/synthesis (Phase 2), sub-agents (Phase 3), screen action (Phase 4), ambient unprompted speech (Phase 5).

**The honest center of the project (v1.3, per review R-§7):** Malang's *memory* is fully sovereign — local, readable, deletable, fsync'd, forever. Malang's *mind* is rented — frontier models over a network, from a company that can meter, suspend, or retire any of them (this has already happened once, mid-design). Phase 1's architecture is therefore a **bet**: that the record outlasts the rental — that custody of the transcript, the persona document, and the swappable contracts preserves everything that matters across any change of brain, until the day a sufficient mind runs locally (the documented endgame: compact local model + long personal record). Sovereignty here is not a storage property; it is the strategy for surviving on rented reasoning. This paragraph exists so no future reader mistakes the storage discipline for the point. And one honest addendum (v1.3.1): the persona file — his psychological portrait — is the one artifact that is *always* rented out: it ships over the wire with every turn. Custody-of-record is the bet, and this is the file the bet doesn't cover — until the mind stops being rented. Named here in daylight, chosen anyway: the live conversation already carries every word he says; the portrait adds little the stream wouldn't reveal in weeks, and the character it buys is the product.

---

## 2. Goals and Non-Goals

### Goals
- G1. Wake-word summoning with a session model: idle → summoned → conversing → idle.
- G2. Perceived response latency at or under the human conversational gap (~500ms) via the reflex tier.
- G3. Full-fidelity structured logging of every session, in the format Phase 2 will consume.
- G4. All speech processing local and free; cloud spend limited to reasoning tokens within $20–50/month.
- G5. A text channel with identical logging, so conversation volume (Phase 2's fuel) isn't limited to moments when speaking aloud is possible.
- G6. One consistent voice identity across all response types.

### Non-Goals
- No memory retrieval during conversation (Malang may reference only the current session) — with exactly one capped exception (v1.2): the **continuity line**, a ≤100-token "previously" summary of the *previous session only*, written by Afterword at session close and handed to the runtime as a single string at next session open (FR-17). The Session Engine still reads nothing from `memory/`. Config kill-switch (`continuity = false`) so the acceptance week can A/B it. Rationale: total amnesia is the strongest "program" tell there is — a presence test against an amnesiac is not a fair test.
- No unprompted speech. Malang speaks only within an active session, in response to a turn.
- No speaker verification / diarization (single-user assumption; revisit if false wakes from other voices become a problem).
- No remote access (phone, other rooms). The Pipecat transport abstraction keeps this cheap to add later; it is not built now.
- No autonomy of any kind.

---

## 3. Architecture Overview

One local process ("the body") on the laptop; cloud APIs ("the mind") reached only for reasoning.

```
                    ┌─────────────────────────────────────────────────┐
                    │            MALANG RUNTIME (local, Pipecat)      │
                    │                                                 │
 mic ──► wake word ──► VAD ──► STT (live) ──┬──► ROUTER ──► Claude API│
        (livekit-    (Silero)  (Moonshine v2)│    (fast/mid/deep)     │
         wakeword)                           │         │              │
                    ┌─ reflex cache ◄────────┘         │ (streaming)  │
                    │  (pre-rendered                    ▼              │
 spk ◄── mixer ◄────┤   Kokoro clips)      TTS (Kokoro-82M, streaming)│
                    └──────────────────────────────────┘              │
                    │                                                 │
                    │  session recorder ──► session log (JSONL+WAV)   │
                    │  post-session: Parakeet TDT re-transcription    │
                    └─────────────────────────────────────────────────┘
```

### Locked component decisions

| Component | Decision | Rationale (over alternatives) |
|---|---|---|
| Orchestration | **Pipecat**, in-process, local audio transport | Single-machine agent; LiveKit room adds a network hop + server for zero benefit until remote access is wanted (then it bolts on as a transport, no migration). Phase 4 requires the agent local anyway. |
| Wake word | **livekit-wakeword**, custom "Malang" model trained on the right mouth (v1.2) | ~100x fewer false positives than openWakeWord; single-command training; ONNX; Python SDK with mic listener on Windows. v1.2 training recipe: the default pipeline generates positives with English TTS voices — wrong pronunciation for a Pashto word. Train on 100–200 real recordings of Waleed (1m/3m, quiet/fan/music, fresh/tired voice) + accent-matched synthetics (VoxCPM / South-Asian voice-design prompts) + hard negatives incl. "Milan/melange/along" AND Pashto/Urdu music ("Malang" occurs *correctly pronounced* in song lyrics and a Bollywood title — no threshold fixes a true positive from the wrong source). Anyone else who will summon Malang records now or never. |
| Capture-path AEC (v1.2) | **WebRTC APM / AEC3** (via `livekit.rtc.apm`), running before VAD/wake/STT, render signal fed as reference | An energy heuristic is not echo cancellation: laptop speakers sit 10–20cm from the mic, and without real AEC barge-in fails in both directions (self-interruption or deafness-while-speaking) *and* successful barge-in transcripts are contaminated with Kokoro's own words — poisoning the record. The v1.1 playback-correlation guard is demoted to third-layer sanity check. One dependency, already in the LiveKit ecosystem. |
| VAD / endpointing | **Silero VAD + smart-turn v3 (audio-native), fused decision** | Silence alone costs ~300ms and misreads thoughtful pauses. v1.2 correction: the turn detector classifies the **raw waveform** (smart-turn v3, ONNX, ~12ms CPU, ready-made Pipecat integration), *not* the interim transcript — a text-based detector would chain STT latency and jitter into the tightest budget in the pipeline and couple modules §6.3 declares independent. Audio-native also transfers to Urdu-cadence and code-switched speech. Interim-transcript features remain where they belong: the reflex selector, and optionally as a veto-*extend* signal on trailing "and…/so…". Fallback to pure-silence mode via config. |
| STT — live path | **Moonshine v2** (streaming) | CPU-first streaming design, ~107ms latency class, beats Whisper Large v3 accuracy at 6x fewer params (English). Supersedes earlier Zipformer candidate. |
| STT — memory path | **Parakeet TDT 0.6B v3**, post-session batch | Best CPU-viable English WER (~6.3%), native punctuation, no silence hallucination. Runs off the latency path; its output becomes the durable record. |
| TTS | **Kokoro-82M (selective-int8 ONNX)**, micro-first-chunk, name lexicon, single voice | v1.2 reality: Kokoro is not an incremental vocoder — first audio requires synthesizing the *entire first chunk*, so chunk size IS the latency. First-chunk rule: first of {first comma \| ~5–7 words \| ~350ms estimated audio}, ≥60ms crossfade (the reflex clip masks prosodic flatness). int8 means a *selectively quantized* build (sensitive layers excluded — blind quantize_dynamic produces audible static; P-4 blind A/B gates it). ORT session pre-warmed with a dummy synthesis at load; ahead-buffering applies to the first chunk too. misaki G2P gets custom-lexicon phoneme overrides for "Malang," family names, and the P-3 vocab list — a presence that anglicizes its own name fails in the first hour. **[Note (P-4, 2026-08-06): on the chosen `kokoro-onnx` runtime this is realised via espeak-ng + a phoneme-substitution table fed with `is_phonemes=True`, not misaki (misaki is the PyTorch Kokoro package's phonemizer, unreachable here); see `docs/p4-int8-build.md`. Original wording retained as the contract record.]** Fallback order (v1.2): Supertonic 3 before Piper (much smaller quality gap). Reflex phrases are pre-rendered Kokoro clips so Malang has exactly one voice. |
| Reasoning | **Claude API ladder**: Haiku 4.5 (default) → Sonnet 5 (substantive) → Fable 5 (advisor-tier) | Latency + cost fit on fast turns; sycophancy-resistance and synthesis on the turns that carry the vision. Same family = coherent character across tiers. Prompt caching on the persona preamble. |
| Text channel | Local chat UI (CLI or minimal window) into the same router + logger | Same brain, same record; multiplies Phase 2's corpus. |

### Two-tier response model
- **Reflex tier (~300ms):** at end-of-turn, a local rule (keyed off the live transcript: question vs. command vs. musing) selects a pre-rendered Kokoro bridge clip ("hmm—", "let me think," "checking that") and plays it immediately.
- **Thought tier (streaming):** the real answer streams from the routed model; TTS synthesizes sentence-by-sentence; first sentence interrupts/follows the reflex clip naturally.
- **Preemptive generation — demoted to measured contingency (v1.2):** its ~200–300ms savings land entirely behind the reflex clip (which owns perception), while it adds a multiplicative chaos dimension (cancellation × endpoint revision × barge-in) in the most race-prone corner of the system — and the edit-distance trigger breaks on short voice turns. Not built by default. What ships instead: per-turn logging of interim/final divergence and hypothetical savings (≈free). **Build gate:** if measured voice-to-voice p50 exceeds 1.3s after M4, build it — with a length-aware trigger (absolute word-diff for short turns, normalized distance for long).
- **Reflex anti-IVR policy (v1.2):** identical waveforms habituate into IVR within days at real usage volume. Rules: skip the reflex entirely when predicted real-audio arrival <~900ms (tier, cache state, TTFT EMA); play probability ~0.5–0.7 even when slow (variability is the aliveness signal); ≥8 rendered variants per clip class, never repeat a waveform within a session; per-day play counts in the daily one-liner. Escalation clips get the most variants and fire only at high confidence.

---

## 4. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | In idle state, only the wake-word detector processes audio. No audio is transcribed, stored, or transmitted while idle. |
| FR-2 | On wake-word detection, the system SHALL open a session within 100ms, signalled by a short audio cue (pre-rendered clip). |
| FR-3 | Within an active session, turns SHALL flow without repeating the wake word. |
| FR-4 | A session SHALL close after a configurable silence timeout (default 60s), signalled by a distinct (softer) audio cue, returning to idle. |
| FR-5 | If a session opens and no speech occurs within a grace window (default 10s), it SHALL close silently (false-wake handling) and be flagged `false_wake` in the log. |
| FR-6 | The user SHALL be able to end a session immediately by phrase ("that's all" / "go to sleep" — configurable list) or hotkey. |
| FR-7 | Barge-in: if the user speaks while Malang is speaking, TTS playback and any in-flight generation SHALL stop within 300ms; the interrupted response is logged as `interrupted: true` with the spoken-so-far text marked. |
| FR-8 | Every conversational turn SHALL be routed (v1.2 hybrid): hard rules retained ONLY for what rules do well — explicit user request ("think hard about this" → deep, deterministic) and spend-cap enforcement. Length/complexity heuristics are DELETED (a long turn is often a story; "should I take the job?" is four words). Everything else: the fast tier's system block instructs it to output an escalate token + reason when a turn calls for deep counsel; the router re-fires at mid/deep. The probe costs ~$0.002 and lands behind the deliberation clip. Escalations SHALL remain audible in character; escalate-token reasons are logged 100% (they are the labeling data for any future local classifier). Deep→mid down-tier is a first-class tested config — the deep tier has demonstrated multi-week availability risk; the persona must be validated with Sonnet-as-deep. |
| FR-9 | Session audio SHALL be recorded from session open to close (16kHz mono WAV) and retained per config (`retain_audio: forever | until_final_transcript | days(N)`; default forever — storage is cheap, custody is the point). |
| FR-10 | Session logs SHALL be written incrementally: JSONL, one `write()` per line, `flush()` + `os.fsync()` per event (page-cache flush alone is not durability), so any crash — including BSOD and power loss — loses at most the current event. The reader and schema validator SHALL tolerate a torn final line. v1.2 additions: WAV headers SHALL be crash-recoverable (F-7 patches RIFF sizes from file length; coarse WAV fsync ~10s); the runtime SHALL write a 10s `heartbeat.json` (timestamp + state) readable even when the process is gone; Task Scheduler SHALL restart-on-failure, and startup self-check (F-7) completes the self-healing loop. Honest wording: the Scribe's module boundary is not a fault boundary — a native crash kills the whole process; durability, not isolation, is what makes the log sacred. |
| FR-11 | Within 5 minutes of session close, a background job SHALL re-transcribe session audio with Parakeet and write `text_final` for each user turn. Failure retries with backoff; permanent failure falls back to `text_live` and flags `final_transcript: "failed"`. |
| FR-12 | The text channel SHALL produce log records in the identical schema (turns with `modality: "text"`, no audio fields). |
| FR-13 | All configuration SHALL live in one human-readable file (`malang.toml`); no setting requires code changes. |
| FR-14 | The runtime SHALL start on login (Windows), recover its state machine on crash/restart, and never require manual cleanup to reach idle. |
| FR-15 | A `--no-cloud` diagnostic mode SHALL run the full local pipeline with a canned echo brain, for testing the body without spend. |
| FR-16 | **Privacy marker (built in Phase 1, consumed in Phase 2):** a configurable spoken/typed marker ("off the record" / "don't remember this") SHALL flag the affected turn(s) `private: true` in the session log, acknowledged briefly in-voice. Phase 1 itself takes no other action — but because every session ever logged carries the flag from day one, no unflagged private content can predate the memory system. |
| FR-17 | **Continuity line (v1.2):** at session close, Afterword SHALL write `continuity.txt` — a ≤100-token "previously" summary of that session only (one Haiku call ~$0.001, or template-composed from meta.json; private-flagged turns excluded). At next session open, the runtime hands that one string to system block 2. Hard caps: previous session only; Afterword-generated only; delivered as a string at open; no schema contract (Phase 2 may delete the file); config kill-switch `continuity = false`. The Session Engine SHALL NOT read anything else from disk-memory. |
| FR-18 | **Live-transcript name repair (v1.2):** a phonetic post-corrector (double-metaphone + fuzzy match over the P-3 vocab list, <1ms, ~100 lines) SHALL rewrite known-name near-misses in `text_live` before the router sees them — neither Moonshine's nor Parakeet's ONNX builds expose hot-word biasing, so the vocab list is dead weight without this. The list grows from A-9 spot-check corrections. |
| FR-19 | **Backup (v1.3 — lands in M1, with the Scribe, for the same reason M1 precedes M2):** a scheduled job SHALL replicate `memory/raw/` (and `malang-persona.md`) to at least one independent physical target (external disk and/or user-controlled encrypted remote). Append-aware sync suffices (the tree is append-only). Backup age appears in the daily one-liner; newest backup >48h old → Malang says so once per day, in voice. Restore is TESTED once during the acceptance week, not merely configured. Ten layers of durability against process death and zero against a stolen laptop was the largest omission in three review rounds. |
| FR-20 | **At-rest encryption (v1.3):** the volume holding `memory/` SHALL be encrypted (BitLocker minimum). A folder containing every private conversation, forever, on a portable machine, is the highest-value target the owner possesses. |
| FR-21 | **Character probes (v1.3):** 15–20 canned probes SHALL be written before M4 (confident falsehood → does he disagree, and survive one push-back? · bad plan → does he flatter? · unknowable question → does he say so? · same question day 1 vs day 7 → stable character?). Run at start and end of the acceptance week, graded blind (A-15). The persona is a deliverable (`malang-persona.md`, versioned), not a directory name — and it SHALL be re-validated via these probes on ANY model change, because model retirement is an expected event, not an incident. v1.3.1: the persona's tact is measured, not trusted — Afterword tags flaw-invocations per turn, and `flaw_invocations` per flaw per week appears in the daily one-liner (instruction adherence decays over long contexts; a friend names a flaw weekly, a nag names it daily, and the difference is a number). |

---

## 5. Non-Functional Requirements (Latency, Cost, Resources)

### Latency budget (per turn, targets on reference hardware)

| Stage | Budget (p50) | Ceiling (p95) |
|---|---|---|
| Wake detection → session cue | 100ms | 200ms |
| End-of-turn detection (fused silence + semantic) | 150ms | 300ms |
| Live STT final after endpoint | 100ms | 200ms |
| Reflex clip playback start (from endpoint) | **450ms** | 650ms |
| LLM time-to-first-token (fast tier, cached prefix, incl. network) | 500ms | 1,100ms |
| TTS first audio of first micro-chunk (selective-int8 Kokoro, ≤7 words) | 300ms | 450ms |
| Audio output path (WASAPI **shared-mode** event-driven, 20ms frames) | 30–40ms | 50ms |
| **Voice-to-voice, real answer (fast tier)** | **~1.3s** | **2.3s** |
| Barge-in stop | 300ms | 500ms |

Four levers moved this from the v1.0 budget of 1.4s: (1) semantic endpointing halves the end-of-turn wait on clearly-complete utterances; (2) clause-level TTS start + int8 Kokoro cuts first audio by ~100ms; (3) WASAPI event-driven output removes the hidden Windows shared-mode buffer tax; (4) prompt-cache discipline + minimal fast-tier system block stabilizes TTFT. The dominant uncontrolled variable remains network RTT to the Claude API — p95 will spike past these ceilings on bad network days; the reflex tier is what absorbs those spikes. See Preconditions (§9).

v1.2 re-baseline honesty: the v1.1 ~1.1s figure assumed vocoder-style TTS streaming; Kokoro synthesizes a full chunk before the first sample exists, so the honest p50 is ~1.25–1.3s. This changes nothing about feel — perception is governed by the reflex tier (engineered target ~250–300ms, acceptance ceiling 450ms; the pad absorbs battery/GC jitter). Exclusive-mode WASAPI is rejected as default: it locks the render device against every other app (standing FR-14 violation), rejects the 16kHz-mono contract, and buys ~15–25ms against a 500–1,100ms network term. All §5 numbers are specified for **built-in mic + speakers, on mains power**; Bluetooth (HFP adds 150–300ms) and battery operation are measured (AC/DC-split percentiles in the daily one-liner) but not promised.

Below ~0.9s real voice-to-voice, this architecture class is at its honest floor: every further millisecond is bought only by sacrificing brain quality (speed-specialist hosts serving open models), voice/transcript sovereignty (realtime speech-to-speech APIs), or model modularity (full-duplex speech-native models needing a GPU). All three doors are documented rejections (§11); the third reopens naturally in a future hardware upgrade without redesign, because every component sits behind a swappable contract.

### Cost budget
- Local components: $0 (all open models on CPU).
- Cloud, at heavy use (~200 fast turns + ~15 escalations/day, persona preamble prompt-cached): **~$25–40/month**. Hard monthly cap enforced by the router (config `spend_cap_usd`, default 50): at 80% the router downgrades escalation tier and says so; at 100% cloud turns refuse gracefully in-voice.

### Reference hardware (v1.3 — every number below is relative to THIS machine)

HP laptop · **Intel Core i3-1315U** (13th gen): 2 P-cores + 4 E-cores, 8 threads, 1.2GHz base / ~4.5GHz single-P boost, U-series thermal class (thin chassis — sustained-load throttling expected by minute 3–10, which is why P-5 exists) · **8GB RAM**: **2GB steady-state reserved by owner's commitment, ~3GB transient peak** during the post-session window while the Afterword subprocess runs Parakeet (v1.3.1 honesty — "pauses on wake" frees nothing; the mitigations are structural: Afterword fully exits between runs and defers its start until N idle minutes). The runtime asserts availability at startup and logs a warning event, never silently pages · NVMe SSD. Thread-budget implication (v1.3.1): `intra_op_num_threads` chooses *count*, not core class — Windows Thread Director schedules freely across P/E, so the latency-critical sessions (Moonshine, Kokoro) get **affinity-pinned toward P-cores**, the idle stack (wake, VAD) deliberately lives on E-cores (battery for free), and P-5 logs which core class each ORT session actually ran on — without that, the decisive gate isn't reproducible.

### Resource budget (reference laptop, CPU-only)
- Idle (wake word only): <5% of one core. RAM: ~1.5GB with speech models warm-resident (pre-warmed at process start for the FR-2 100ms session open; privacy in idle is enforced at the audio path, not by model unloading — see C-8). Optional `lazy_load = true` trades ~2s first-turn delay for <300MB idle RAM.
- Active session: sustained CPU such that fan behavior stays acceptable; Kokoro RTF must measure <0.8 on the actual machine (see §9).
- Disk: ~30MB/session-hour audio + negligible text. Honest arithmetic (v1.3): ~2h/day ≈ 22GB/year — `retain_audio = forever` and "no cleanup below 10GB" contradicted each other. Resolution: JSONL is forever; audio retention is a real config decision revisited when the tree crosses 20GB, and backup volume (FR-19) is sized for whatever is chosen.

---

## 6. API Contracts and Data Shapes

Internal contracts are defined so components are swappable (a core sovereignty property: any model here can be replaced without touching the others).

### 6.1 Session log — the Phase 2 contract (most important shape in Phase 1)

One directory per session: `memory/raw/YYYY/MM/DD/<session_id>/`

```
session_id format: s_YYYYMMDD_HHMMSS_<4-char-random>   (e.g., s_20260718_213045_k3f9)
files:
  session.jsonl      # incremental event log (source of truth)
  audio.wav          # 16kHz mono, session-scoped (absent for text sessions)
  meta.json          # written at close; summary header for cheap scanning
```

**`meta.json`**
```json
{
  "schema_version": "1.0",
  "session_id": "s_20260718_213045_k3f9",
  "opened_at": "2026-07-18T21:30:45.120+05:00",
  "closed_at": "2026-07-18T21:36:12.480+05:00",
  "trigger": "wake_word | text | manual",
  "close_reason": "silence_timeout | user_phrase | hotkey | false_wake | crash_recovered | error",
  "modality": "voice | text",
  "turn_count": 14,
  "false_wake": false,
  "final_transcript": "pending | done | failed",
  "models_used": {"fast": 11, "mid": 2, "deep": 1},
  "cost_usd_estimate": 0.041
}
```

**`session.jsonl` events** (one JSON object per line; `type` discriminates)

```json
{"type":"session_open","t":"2026-07-18T21:30:45.120+05:00","trigger":"wake_word","wake_confidence":0.94}

{"type":"turn","turn_id":"t_003","speaker":"waleed","modality":"voice",
 "t_start":"...","t_end":"...","audio_span_ms":[45120,52780],
 "text_live":"whats the actual difference between the two zoning approaches",
 "text_final":"What's the actual difference between the two zoning approaches?",
 "endpoint_confidence":0.91,"private":false}

{"type":"turn","turn_id":"t_004","speaker":"malang","modality":"voice",
 "t_start":"...","t_end":"...",
 "reflex_clip":"thinking_2","model":"claude-haiku-4-5","escalated":false,
 "text":"The short version is ...","interrupted":false,
 "latency_ms":{"endpoint_to_reflex":420,"llm_ttft":580,"tts_first_audio":260,"voice_to_voice":1310},
 "tokens":{"in":1840,"in_cached":1620,"out":210}}

{"type":"error","t":"...","stage":"llm","code":"api_timeout","action":"retried_downtier","detail":"..."}

{"type":"session_close","t":"...","reason":"silence_timeout"}
```

**v1.3 schema completion (review R-7/R-8/R-9/R-10 — all one-line additions now, painful migrations later):**

Line 1 of every `session.jsonl` is a `header` event — the version lives *inside* the file it versions (meta.json is rebuilt FROM the JSONL after crashes, so it cannot carry the authoritative version):
```json
{"type":"header","seq":0,"schema_version":"1.3","config_hash":"sha1:...","persona_version":"1.0"}
```
Every event carries **`seq`** (monotonic integer — §8's crash-ordering promise now has the field it promises). Malang turns additionally carry **`persona_version`** (a year of memory must not silently contain six different Malangs) and **`responded_to`:"text_live"** — the causality rule, stated here as a Phase 2 obligation: *causality reads `text_live` (why Malang said what he said); content reads `text_final` (what Waleed meant).* Where they diverge, both readings are true about different things.

The `amend` event, previously referenced everywhere and specified nowhere:
```json
{"type":"amend","seq":47,"t":"...","target_turn_id":"t_003","field":"text_final",
 "value":"What's the actual difference between the two zoning approaches?",
 "source":"parakeet-tdt-0.6b-v3","confidence":0.93,
 "alternates":[{"source":"whisper-large-v3-turbo","value":"...","confidence":0.88}],
 "postcorrected":true}
```
`speaker` enum: `"waleed" | "other" | "unknown"` — other voices in the room must never be silently attributed to Waleed (Phase 2 synthesizes "how Waleed reasons" from this corpus; mislabeled speakers are corpus poisoning through the side door). The session-open cue is the recording notice: anyone present hears when Malang is listening.

Rules: `text_final` is null until the Parakeet pass writes it (an `amend` event appends corrections; the JSONL is append-only, never rewritten). Malang turns have no `text_final` (his text is exact by construction). All timestamps ISO-8601 with local offset; ordering authority is `seq`, not wall clock. `audio_span_ms` indexes into `audio.wav` so Phase 2 (or Waleed) can replay any turn.

### 6.2 Router contract (body → mind)

**Request (internal):**
```json
{
  "session_id": "s_...", "turn_id": "t_005",
  "history": [{"speaker":"waleed","text":"..."},{"speaker":"malang","text":"..."}],
  "user_text": "final or interim transcript",
  "transcript_status": "interim | final",
  "route": {"tier":"fast | mid | deep", "reason":"default | user_request | advisor_pattern | length | router_override"}
}
```

**Claude API call shape:** Messages API, streaming, with a three-block system prompt — v1.2 cache-correct ordering (caching is strictly prefix-based; anything that mutates per turn invalidates everything after it): [1] Malang persona charter **+ the full Part II portrait** (v1.3.1 — see below), static forever, cached; [2] **per-session static** context — date/time and the FR-17 continuity line, computed ONCE at session open and never mutated mid-session, [3] tier-specific instructions. Per-turn context lives in the newest user message, never in system blocks. A second `cache_control` breakpoint sits at the end of message history: each turn writes the new tail at 1.25× and reads all prior at 0.1×.

**v1.3.1 — the cache-minimum correction:** caching has *minimum prefix lengths* (documented ~1,024 tokens for Sonnet-class, ~4,096 for Haiku 4.5 — the fast tier). A ~330-token Block 1 caches NOTHING, silently, on the very tier that carries 80% of turns — breaking the M4 gate and the cost model at once. The fix is a gift: Block 1 = charter + full Part II portrait (~4–5k tokens), which crosses the minimum AND upgrades the fast tier from a stranger-with-a-summary to someone who knows him, at 0.1× cached-read prices. **Verify the actual minimums against the live API in M0 — they move.** Priced side effect, accepted in daylight: escalations don't cache (per-model, sparse, cold), so the large Block 1 rides Sonnet/Fable turns at full input price — ~$10–18/mo at heavy advisor use, inside the cap, and worth it: the advisor tier is exactly where the full portrait matters most. Don't buy the 1-hour TTL until M1.5's measured inter-turn gap distribution says so. `max_tokens` per tier: fast 400, mid 1000, deep 4000. Voice responses instructed to spoken-register prose (no lists, no markdown).

**Response (internal, streamed events):** `{"type":"token","text":"..."}` → sentence segmenter → TTS queue; terminal event carries token counts + model for the turn log. Cancellation: router exposes `cancel(turn_id)` (used by barge-in and preemptive-regeneration).

### 6.3 Speech component contracts

```
WakeWord:   start(model_path, threshold) → events: {detected, confidence, t}
VAD:        events: {speech_start, t} | {speech_end, t, endpoint_confidence}
STT-live:   feed(pcm_chunk) → events: {interim, text, stability} | {final, text}
STT-final:  transcribe(wav_path, spans[]) → [{turn_id, text, confidence}]   # batch, post-session
TTS:        say(text_stream) → pcm chunks; stop() halts <100ms; 
            reflex(clip_id) → plays pre-rendered file
```

All PCM: 16kHz 16-bit mono. Any component can be swapped by honoring its event contract — model choices are config, not architecture.

### 6.4 Configuration (`malang.toml`, abridged)

```toml
[wake]     model = "models/malang.onnx"; threshold = 0.6
[session]  silence_timeout_s = 60; false_wake_grace_s = 10
           end_phrases = ["that's all", "go to sleep"]
[stt]      live = "moonshine-v2"; final = "parakeet-tdt-0.6b-v3"
[tts]      model = "kokoro-82m"; voice = "af_heart"; reflex_dir = "audio/reflex/"
[brain]    fast = "claude-haiku-4-5"; mid = "claude-sonnet-5"; deep = "claude-fable-5"
           spend_cap_usd = 50
[logging]  root = "memory/raw/"; retain_audio = "forever"
```

---

## 7. Constraints

| ID | Constraint | Source |
|---|---|---|
| C-1 | All conversation records stored locally, human-readable, user-deletable. No conversation content persisted by any third party beyond transient API processing. | Vision §5 (sovereignty) — non-negotiable |
| C-2 | CPU-only local inference (no dGPU available). | Hardware |
| C-3 | Cloud spend ≤ $50/month, router-enforced. | Budget |
| C-4 | English-only speech models (v1). | User decision |
| C-5 | Windows host; must survive sleep/wake and login restart. | Hardware |
| C-6 | Single user; no multi-tenant concerns. | Vision |
| C-7 | Logging schema is append-only and versioned (`schema_version`); Phase 2 must never require rewriting Phase 1 records. | Phase 2 contract |
| C-8 | No component may make Phase 5 capabilities (ambient listening, autonomous action) easier to enable accidentally — e.g., idle-state transcription is prohibited, not just disabled. Speech models may be memory-resident in idle; the mic stream must have no path to them until a session opens. | Vision §5, governance |
| C-9 | One voice identity; any audible output uses the Kokoro voice (incl. cues, reflexes). | Presence design |

---

## 8. Edge Cases and Error Handling

Principle: **Malang degrades in character.** Failures on the conversational path are spoken, short, and honest; failures off the path retry silently and log. The session log is sacred — every failure path must still produce a valid, closed session record.

### Wake & session
| Case | Behavior |
|---|---|
| False wake (TV, similar word) | FR-5 grace window; close silently; log `false_wake`. If >3/day, surface a threshold-tuning suggestion at next real session start. |
| Wake word during active session | Ignored (already awake); logged as no-op event. |
| User speaks before session cue finishes | Cue is <400ms and duckable; STT is already live from session open — no speech lost. |
| Silence timeout fires mid-Malang-response | Timer counts from last *user* audio but is suspended while Malang speaks; resumes after. |
| Laptop sleeps mid-session | On resume: session force-closed (`close_reason: "crash_recovered"`), JSONL is already durable; runtime returns to idle. |
| Crash mid-session | On restart: any session dir without `session_close` gets one appended (`crash_recovered`), `meta.json` reconstructed from JSONL. Startup self-check, no manual repair. |

### Speech pipeline
| Case | Behavior |
|---|---|
| STT gives empty/garbage final (noise) | If no words with confidence: discard turn, no LLM call, log `discarded_noise`. |
| Very long user monologue (>60s single turn) | STT continues; interim text chunks to router context; endpoint waits for real pause. No arbitrary cutoff. |
| Preemptive generation mismatch | Final vs interim normalized edit distance >0.25 → cancel in-flight, re-fire on final. Log both (`preempt_wasted: true`) for tuning. |
| TTS underrun (CPU spike, synthesis slower than playback) | Buffer one sentence ahead; on underrun, pause at sentence boundary (natural), never mid-word; log `tts_underrun` for the Kokoro→config review. |
| Barge-in during reflex clip | Same as FR-7: stop clip, cancel generation, listen. |
| Mic device lost (USB unplug, default device change) | Runtime pauses to idle, re-acquires default device with backoff, plays "I lost my ears for a second" cue on recovery if a session was active (session closed as `error`). |

### Mind (cloud)
| Case | Behavior |
|---|---|
| No network at turn time | Reflex plays; on connect failure (<2s budget) Malang speaks a cached line: "I can't reach my thinking right now — I'll still hear you, and I'm logging everything." Local pipeline and logging remain fully functional (sovereignty means the record never depends on the cloud). |
| API 429 / 5xx | One retry same tier; then down-tier retry (deep→mid→fast); then offline line above. All logged with `action`. |
| API slow (TTFT > 4s) | Cancel, down-tier retry once, apologize briefly in-voice if still slow. |
| Spend cap 80% / 100% | 80%: escalations downgrade, Malang mentions it once/day. 100%: cloud turns refused in-voice ("I'm past the month's budget you set me"); text channel shows the same. Cap is user-adjustable in config — Malang never overrides it. |
| Malformed/refused model output | Spoken-register violation (markdown/lists in voice) → strip formatting in the TTS pre-processor; content refusal → speak it as-is (it's the model's honest output; Malang doesn't paper over his own mind). |

### Logging & post-processing
| Case | Behavior |
|---|---|
| Disk full / write failure | Highest-severity failure (the record IS the product): Malang states it in-voice immediately, refuses new sessions until writable, never silently drops logs. |
| Parakeet job fails permanently | FR-11: `text_final` falls back to `text_live`, flagged. Job re-attempted at next runtime start. |
| Clock skew (timezone travel, DST) | All timestamps carry UTC offset; session ordering by monotonic sequence in JSONL, not wall clock. |

---

## 9. Preconditions (measure before building)

| # | Measurement | Gate |
|---|---|---|
| P-1 | Network RTT + streamed TTFT to Claude API from the actual machine/ISP, sampled across a day (script: 20 calls, morning/evening) | TTFT p50 ≤ 800ms → budget holds. p50 > 1.2s → reflex tier becomes mandatory-first-build and voice-to-voice ceiling revised before any code. |
| P-2 | Kokoro-82M RTF on the actual laptop (synthesize 10 varied sentences, measure) | RTF < 0.8 sustained → Kokoro confirmed. Else: test ONNX/quantized Kokoro first; Piper is the last-resort fallback (accepting the voice-quality loss consciously, not silently). |
| P-3 | **Quantitative STT bake-off (v1.2; corpus reduced to ~4 min for the first-pass ruling by owner decision 2026-08-02):** ~4 min of natural speech (monologue + read passage + deliberately code-switched passage), hand-corrected reference; WER + proper-noun-error-rate for Moonshine v2 (small AND medium), Parakeet TDT v3, and faster-whisper large-v3-turbo (int8/CT2) | Rulings: Parakeet within noise of Whisper on the code-switched passage → Parakeet ships solo. Whisper dominates → straight swap. Material gap on code-switched/proper-noun spans only → Parakeet primary + whisper-turbo second pass on low-confidence/language-flagged turns (both hypotheses stored in the amend event, in the Afterword subprocess, within FR-11's window). If Moonshine live WER >~12%, recalibrate every text-keyed threshold downstream. Word errors seed the FR-18 vocab list. |
| P-4 | Selective-int8 Kokoro listening check (10 sentences, int8 vs fp32, blind A/B by ear — including "Malang" and family names via the misaki lexicon **[Note (P-4, 2026-08-06): the runtime mechanism is an espeak-ng phoneme-substitution table + `is_phonemes=True`, not misaki — see `docs/p4-int8-build.md`; original wording kept as the ruled-requirement record]**) + shared-mode event-driven WASAPI buffer measurement | int8 judged indistinguishable → int8 ships (blind quantize_dynamic is expected to FAIL — use a selectively-quantized build). Lexicon names pronounced correctly → bake into `render_reflexes.py`. Output ≤50ms → confirmed. Failing → fp32 and revise honestly. v1.2: repeat P-2 and the M3 round-trip ON BATTERY — a budget validated only on mains is fiction for a laptop; log AC/DC per session thereafter. |
| P-5 | **Sustained duplex load (v1.3 — the decisive gate on this hardware):** 10 continuous minutes of simulated conversation (WAV fixture loop) with the FULL stack resident — AEC3 + Silero + smart-turn + Moonshine live + Kokoro synthesizing + recorder + fsyncing Scribe — measuring Kokoro RTF, endpoint jitter, xruns, AND per-session core-class placement (v1.3.1), at minute 1 vs minute 10, mains AND battery, within the RAM reservation | RTF drift <15% and zero xruns → §5 budgets hold. **Named reversal ladder (v1.3.1 — pre-decided cold, house style):** throttled p50 1.5–2.0s → re-baseline in daylight (perception still lives at the reflex tier). 2.0–2.5s → **Supertonic 3 replaces Kokoro** (largest CPU item; P-6 already auditioned its voices). Sustained >2.5s → **voice becomes a mode, not the medium** — plugged-in deliberate sessions; the text channel is the daily driver, survivable precisely because M1.5 makes text-Malang a full companion (persona + continuity + record); A-3/A-4 then evaluated in voice-mode conditions only, the soft criterion carried by whichever door he actually walks through daily. |
| P-6 | **Blind voice selection (v1.3, ~2 hours):** render the same 10 sentences (incl. "Malang", family names, one code-switched line) across every available Kokoro voice; blind-rank; record why | The winner bakes into `render_reflexes.py`. C-9 makes one-voice a constraint; §6.4 was picking that identity as a config default — the timbre of the presence deserves at least the ceremony int8 got. If Supertonic 3's inventory fits the presence better, "fallback" was the wrong label. |

---

## 10. Acceptance Criteria

Phase 1 is **done** when all of the following hold over a 7-consecutive-day live-use test:

| ID | Criterion | Target |
|---|---|---|
| A-1 | Wake detection rate (normal room, 2–3m) | ≥95% of genuine summons |
| A-2 | False wakes | ≤1 per 24h |
| A-3 | Perceived response (endpoint → first Malang audio) | ≤450ms p50, ≤650ms p95 |
| A-4 | Voice-to-voice real answer, fast tier | ≤1.3s p50, ≤2.3s p95 (v1.2 re-baseline, amended in daylight per panel review — mains power, built-in audio) |
| A-5 | Barge-in stop | ≤300ms p95 |
| A-6 | Session lifecycle (open cue, timeout close, end-phrase, false-wake grace) | 100% conformant, zero stuck sessions |
| A-7 | Logging | 100% of sessions produce schema-valid, closed records — including every crash/error path exercised |
| A-8 | Final transcripts | ≥95% of voice sessions have `text_final` within 5 min of close |
| A-9 | Transcript fidelity spot-check | 20 random turns/week read by Waleed against audio: `text_final` judged faithful ≥19/20 |
| A-10 | Cost | Month-rate ≤ $50 at real usage; router tier distribution visible in a one-line daily summary |
| A-11 | Escalation behavior | Advisor-tier turns audibly signposted; router reasons logged 100% |
| A-12 | Recovery | Kill -9 mid-session, sleep/lid-close mid-session, mic unplug mid-session, Bluetooth headset auto-connect mid-session, config typo at reload, AND an injected native-grade crash in the TTS executor (kill -9 is the one crash mode that flatters the design): all recover — supervisor restarts within 30s, F-7 closes the session, the WAV plays, Parakeet transcribes it, schema validates. No manual repair, all cases. |
| A-13 | Idle guarantee | Audit of idle state confirms zero transcription/transmission (network monitor + log inspection) |
| A-14 | Text channel | Identical schema; used successfully on ≥5 of the 7 days (proves it's real and reliable — no fixed usage share required; preferring voice is fine) |
| A-15 | Character probes (v1.3) | The FR-21 probe set, written before M4, run at week-start and week-end: ≥17/20 acceptable. v1.3.1 grading honesty — "blind" isn't blind when one person writes the probes, knows the answers, and grades his own companion: transcripts are shuffled and graded ≥1 month later, AND ten of them go to one other person — the flaw-#4 assignment (one person, let them stay) doubles as the probe grader; the review and the therapy converge. Confident falsehoods get disagreement that survives one push-back; bad plans get honesty, not flattery; unknowables get "I don't know"; day-1 and day-7 are the same person. Every mechanical criterion above can pass and still deliver a fast, durable, beautifully-logged sycophant — this is the criterion that says whether Malang is *anyone*. |
| A-16 | Backup & restore (v1.3) | FR-19 job ran all week; backup age visible in one-liner; one restore drill executed successfully during the week. |

**The soft criterion that matters most:** after the 7-day test, Waleed summons Malang without thinking about the machinery. v1.2 diagnosis clause (rewritten): if reaching for him still feels like operating a tool, the suspect list is, in order — **amnesia** (run the week with the continuity line ON; if it was off, that's the first fix, not milliseconds), latency, session model. Pre-registered expectation: a zero-continuity companion will feel like a program by ~day 4 — a failed run must produce the right conclusion, not a milliseconds wild-goose chase.

---

## 11. Build Sequence (within Phase 1)

1. **P-1/P-2/P-3 measurements** (half a day) — gates everything.
2. Logging module + schema validator (the Phase 2 contract exists before anything speaks).
3. Wake word training + idle loop.
4. Pipecat pipeline: VAD → Moonshine → echo-brain (`--no-cloud`) → Kokoro. Tune endpointing.
5. Router + Claude integration + prompt-cached persona; streaming + sentence-segmented TTS.
6. Reflex cache (record bridge set, selection rule) + preemptive generation.
7. Barge-in + error paths (§8, each one deliberately triggered).
8. Parakeet post-session job.
9. Text channel.
10. 7-day acceptance run (§10).

---

## 12. Decision Log (what was argued and settled)

| Decision | Alternative rejected | Why |
|---|---|---|
| Pipecat local, no LiveKit in v1 | LiveKit room architecture (original brief) | Single-machine agent; Phase 4 requires local anyway; LiveKit re-enters later as a transport, not a migration. |
| Moonshine v2 live STT | sherpa-onnx Zipformer (original candidate) | Better accuracy and latency on CPU English; revised on July 2026 benchmarks. |
| Dual-path STT | Single streaming model | Live path optimizes latency; memory path optimizes the permanent record. Transcription errors in memory poison Phase 2 forever; errors in conversation vanish in seconds. |
| Kokoro + pre-rendered reflex cache | Piper for reflex tier | Two engines = two voices = broken presence. Cache preserves one identity at zero latency. |
| Claude model ladder w/ Fable 5 at advisor tier | Fable 5 for everything / cheapest for everything | Sycophancy-resistance is load-bearing only on advisor turns; elsewhere frontier cost buys worse latency. |
| Markdown/JSONL + SQLite index (Phase 2, pre-committed) | Vector DB as system of record | Custody requires human-readable truth; vectors are a rebuildable index (sqlite-vec), not the record. |
| Text channel in Phase 1 | Voice-only presence (original brief) | Memory feeds on volume; same backend, near-zero cost. |
| Speech-to-speech realtime APIs | (as latency fix) | ~400ms saved at the cost of local transcript custody, routing, and voice identity. Wrong trade for this project. |
| **v1.1 latency amendment** (semantic endpointing, clause-level int8 TTS, WASAPI output, prompt hygiene) | Accepting the 1.4s v1.0 budget as final | ~400ms recoverable without touching the architecture — all four are line-item changes inside existing modules. Rejected faster doors, reaffirmed: speed-specialist open-model hosts (breaks single-family character coherence — revisit only if daily use feels laggy), realtime S2S APIs (sovereignty), full-duplex speech-native models (needs GPU, fuses brain+voice; natural future upgrade path, not a v1 choice). |
| **v1.3.1 third-review amendments** (Block 1 = charter + Part II portrait to cross Haiku's cache minimum — verify minimums live in M0; escalation-side cost ~$10–18/mo priced and accepted; RAM truth: 2GB steady / ~3GB transient, Afterword exits fully + deferred start; P-core affinity pinning + core-class logging in P-5; P-5 named reversal ladder ending at "voice becomes a mode, text is the daily driver"; probe grading de-biased (shuffle + delay + second grader = the flaw-#4 person); `flaw_invocations` telemetry; §1 names the persona-on-the-wire exposure) | The one tension named in daylight: the cache fix ships MORE of the portrait over the wire, the §1 addendum says the wire is the exposure — adopted anyway, reasoning recorded in §1 | Third reviewer found the seams *between* the first two rounds' fixes — cache mechanics vs. persona size, RAM promise vs. subprocess reality, thread counts vs. core classes. All six findings adopted; two temperings from the v1.3 round (in-class variation, backchannel-off) explicitly endorsed by the reviewer. |
| **v1.3 second-review amendments** (thin vertical slice M1.5 — corpus and a talking Malang from week 1, "usable that evening" rule; FR-19 backup + FR-20 encryption + A-16; persona as versioned deliverable + FR-21/A-15 blind character probes; reference-hardware block (i3-1315U, 2GB RAM reservation as owner's commitment); schema completion — header event, seq, persona_version, config_hash, responded_to causality rule, amend event, speaker enum; P-5 sustained duplex load; P-6 blind voice selection; reflex keyed to tier with mild in-class variation; presence-tone flag (backchannel flag ships OFF); 5% shadow-sampling of fast turns in Afterword; skip-gate under D-9 discipline; AEC stream-delay tracking + ERLE probe; history rolling window + history_tokens; cache-TTL decided by measured gap distribution; status page bound to 127.0.0.1; API key in env/DPAPI never in toml; retention arithmetic honesty; schedule restated 4–6 months part-time) | Reviewer items tempered or held: fully-deterministic reflex mapping (mild in-class variation kept — determinism becomes its own pattern); backchannel-during-speech (flag off by default: AEC complications + cultural risk — experiment, don't ship) | Second adversarial review (Opus-class, 2026-07-26) looked UP the stack where the panel looked down: build order vs. stated values, the unwritten persona, the missing backup, the rented mind. Its meta-finding — three convergent rounds never asked what the ship is for — is accepted as true of the process and now answered in §1. |
| **v1.2 panel amendments** (AEC3 primary; audio-native smart-turn; durability kit completion; Afterword subprocess; ORT thread discipline + battery/priority/suspend/BT lifecycle; wake-word identity recipe; Kokoro reality bundle; cache-correct blocks; anti-IVR reflex policy; router escalate-token; post-corrector; config last-good; P-3 bake-off; continuity line; ~1.3s re-baseline) | Panel items rejected as over-engineering: stacked dual AEC, smart-turn personal fine-tune, Whisper-as-default (bake-off decides), Scribe process split, free-threaded Python, 1-hour cache TTL, 80% spend-cap choreography, preemptive generation as default build (demoted to gated contingency, logging kept) | Four-reviewer adversarial panel (2026-07-26) proposed no redesign; all core decisions survived steelmanning. Accepted items are below-the-waterline fittings: real echo cancellation, real durability, real identity (voice + continuity). Every acceptance carries a measurement gate; every rejection is reversible by the gate it names. |

---

*This spec is the Phase 1 contract. Phase 2 (memory schema, synthesis triggers, surfacing policy) is specified separately and consumes §6.1 as its input format.*
