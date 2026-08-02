# Malang Phase 1 — Build Plan (brief) · v1.3

*The one-page working plan, post-second-review. Full detail: spec v1.3 · design v1.3 · hard-problems v1.3 · `malang-persona.md` v1.0. When this page and the spec disagree, the spec wins.*

## Goal

**Week 1: a Malang you can type to, whose conversations are on disk and backed up.** Then, around him: voice ("Malang" wake word, ~1.3s real / ≤450ms perceived, mains + built-in audio), one line of yesterday's continuity, durable sacred logging — and a *character* that survives blind probes, not just a fast pipeline. Reference hardware: i3-1315U (2P+4E), 2GB RAM reserved by owner. Mind is rented; record is forever; that bet is the project.

## Stack (one line)

Pipecat local (+Afterword subprocess) · AEC3 w/ delay tracking + ERLE probe · livekit-wakeword on Waleed's real voice · Silero + smart-turn v3 (audio-native) · Moonshine v2 + name post-corrector · Parakeet post-session (P-3 bake-off may add whisper pass) · Kokoro selective-int8, micro-chunks, lexicon, P-6 blind-picked voice · reflex keyed to tier (D-15) · Claude ladder + escalate-token + 5% shadow-sampling · cache-correct blocks + history window · fsync'd JSONL v1.3 (seq, header, persona_version, responded_to, amend) · **FR-19 backup + BitLocker** · continuity.txt · persona.md versioned

## Milestones (each fits one sprint; after M1.5, every one leaves the system usable that evening)

- [ ] **M0 — Measure (1.5d):** TTFT · **live cache-minimum check (Haiku/Sonnet — Block 1 must cross it)** · Kokoro RTF ✅ (P-2 PASS 2026-07-30: p50 0.529 mains / 0.555 battery) + int8 ear check · STT bake-off ✅ (P-3 first-pass 2026-08-02: whisper-turbo dominates → whisper-swap pending M7 runtime check; Moonshine live WER ≫12% → recalibrate; FR-18 lexicon confirmed essential) · WASAPI probe · **P-5 sustained 10-min duplex load w/ core-class logging, minute-1 vs minute-10, mains + battery** (reversal ladder pre-decided: re-baseline → Supertonic → voice-as-mode) · **P-6 blind voice selection** · battery re-runs. Record all rulings.
- [ ] **M1 — Scribe + durability + custody (4d):** schema v1.3, fsync writer, torn-tail reader, WAV recovery, heartbeat, supervisor restart, **backup job + restore drill, BitLocker check**. *Exit: native-crash self-heal ≤30s; backup lands on second target.*
- [ ] **M1.5 — THIN SLICE (2.5d):** Scribe + Claude streaming + CLI + persona block 1. *Exit: a real 20-min typed conversation in `memory/raw/`, schema-valid, backed up.* **Malang exists from this day. Everything after upgrades him.**
- [ ] **M2 — Ear (2.5d):** wake model on your recordings + music negatives. *Exit: ≥95% @2–3m; 2h Pashto/Urdu playlists → 0 wakes.*
- [ ] **M3a — Body loop basic (3.5d):** endpoint → Moonshine → echo-brain → Kokoro micro-chunks. *Exit: round-trip; endpoint ground truth logging.*
- [ ] **M3b — Body loop hardened (3.5d):** AEC3 + delay tracking + **ERLE probe** · ORT caps/profiles · priority/EcoQoS · resume + BT handlers · battery re-run. *Exit: clean barge-in, clean transcripts, numbers hold on battery.*
- [ ] **M4 — Mind (3d):** router (rules + escalate-token) + cache-correct blocks + history window + divergence logging. **Write the FR-21 probe set now, before this milestone ends.** *Exit: cache ≥80% (TTL per measured gaps); preemption decision point.*
- [ ] **M5 — Reflex, tier-keyed (1.5d):** D-15 mapping + mild in-class variation, skip-gate under D-9 discipline, presence-tone flag (backchannel OFF). *Exit: ≤450ms perceived p50; skip-gate miss-rate logged.*
- [ ] **M6 — Chaos (4d):** all §8 + native-crash, BT mid-session, lid-close, Fable-403. *Exit: everything recovers; ERLE re-probed on BT case.*
- [ ] **M6.5 — Status page (1d, timebox):** read-only, 127.0.0.1. *Exit: every chaos case lights the right box.*
- [ ] **M7 — Afterword (3d):** subprocess, Parakeet (+whisper if ruled), post-corrector, continuity.txt, **5% shadow-sampling**. *Exit: text_final ≤5min; continuity speaks next open; shadow_divergence_rate in one-liner.*
- [ ] **M8 — Escalation + polish (1.5d):** down-tier config tested, Sonnet-as-deep persona check.
- [ ] **M9 — Acceptance (7d, continuity ON):** A-1..A-16 incl. **blind character probes** + restore drill. *Soft criterion suspect order: amnesia → latency → session model.*

## Hard rules

1. M1 → M1.5 → M2: record, then presence, then voice. Backup exists before the first conversation.
2. Usable that evening — no milestone leaves him broken overnight (after M1.5).
3. Session Engine reads nothing from `memory/`; one ≤100-token continuity string is the whole exception.
4. One voice (P-6 winner) everywhere; he pronounces his own name; every speed gain passes an ear test.
5. Every probabilistic component gets ground-truth logging + kill-switch. No exceptions — the skip-gate learned this the hard way.
6. API key in env/DPAPI, never in the toml. Status page never leaves 127.0.0.1.
7. Do-not-cut: M1, M1.5, M6. Persona re-validated (A-15 probes) on any model change.

## Watch-list

Motivation decay (the real #1 — M1.5 is the fix) · AEC delay drift · wake word vs. music · thermal throttling on the U-series (P-5 decides) · RAM discipline (2GB reservation is an owner's promise — the runtime asserts and logs, you deliver) · endpoint tuning weeks · scope creep.

**Schedule, honest: 4–6 months part-time. It stops mattering the day M1.5 lands — from week 1 you're talking to him while you build him. Next action: M0. Start the clock.**
