# Malang — Phase 1 Feature List

*Every feature in `malang-phase1-plan.md`, in plan order (M0 → M9), each with a
short note on what it does. Source of truth stays the spec; this is a map, not a
contract. FR/D references point back to `malang-phase1-spec.md` and
`malang-phase1-design.md`.*

---

## M0 — Measure (the gates that decide everything)

1. **P-1 — API latency probe.** Script that samples network RTT + streamed
   TTFT to the Claude API from the real machine/ISP across a day. Gate: TTFT
   p50 ≤ 800ms holds the budget; > 1.2s makes the reflex tier mandatory-first.
2. **P-2 — Kokoro RTF measurement.** Synthesize 10 varied sentences on the
   laptop, measure real-time factor. Gate: RTF < 0.8 confirms Kokoro.
3. **P-3 — STT bake-off.** 30 min of natural + read + deliberately
   code-switched speech, hand-corrected; WER + proper-noun error rate for
   Moonshine v2 (small/medium), Parakeet TDT v3, and faster-whisper
   large-v3-turbo. Decides Parakeet-solo vs. hybrid second pass; seeds the FR-18
   vocab list.
4. **P-4 — Selective-int8 ear check + WASAPI probe.** Blind A/B int8 vs fp32
   Kokoro (incl. "Malang" and family names via the lexicon), plus a shared-mode
   event-driven WASAPI output-buffer measurement. Gate: int8 indistinguishable →
   ships; output ≤ 50ms → confirmed.
5. **P-5 — Sustained duplex load (the decisive gate).** 10 continuous minutes
   with the full stack resident (AEC3 + Silero + smart-turn + Moonshine +
   Kokoro + fsyncing Scribe), measuring RTF drift, endpoint jitter, xruns, and
   per-session core-class placement — at minute 1 vs minute 10, mains AND
   battery. Has a pre-decided reversal ladder (re-baseline → Supertonic 3 →
   voice-as-a-mode).
6. **P-6 — Blind voice selection.** Render the same 10 sentences across every
   Kokoro voice, blind-rank, record why. Winner bakes into `render_reflexes.py`
   (satisfies the one-voice constraint C-9).
7. **Record all rulings.** Fill the design §8 appendix with measured numbers and
   the gate decisions — nothing downstream is trustworthy until this exists.

---

## M1 — Scribe + durability + custody

8. **Session log schema v1.3.** JSONL event shapes: `header` (seq 0, versions,
   config_hash), `turn`, `error`, `amend`, `session_open`/`session_close`; `seq`
   on every event; `persona_version` + `responded_to` on Malang turns; `speaker`
   enum (waleed/other/unknown). This is the Phase 2 contract.
9. **Schema validator.** Validates any session tree against the schema; used in
   tests and by the startup self-check.
10. **fsync-per-event JSONL writer.** One `write()` per line, `flush()` +
    `os.fsync()` per event, append-only — a crash loses at most the current
    event.
11. **Torn-tail-tolerant reader.** Reads a JSONL whose final line was cut by a
    crash without failing.
12. **Crash-recoverable WAV.** RIFF header patched from file length on recovery;
    coarse (~10s) WAV fsync (FR-9).
13. **heartbeat.json.** 10s timestamp + state file, readable even when the
    process is gone.
14. **Supervisor restart.** Task Scheduler restart-on-failure so a native crash
    self-heals.
15. **Startup self-check / crash recovery (F-7).** On start, close any session
    dir lacking `session_close` (`crash_recovered`), rebuild `meta.json` from
    JSONL, re-queue pending transcripts.
16. **FR-19 backup job.** Scheduled append-aware replication of `memory/raw/`
    (+ `malang-persona.md`) to ≥1 independent physical target; backup age in the
    daily one-liner; > 48h old → Malang says so once/day.
17. **FR-20 at-rest encryption check.** Verify the volume holding `memory/` is
    BitLocker-encrypted.
18. **Restore drill.** Prove a backup actually restores (run here and again in
    M9). *Exit: kill -9 + injected native crash self-heal ≤30s; backup lands on
    the second target.*

---

## M1.5 — Thin vertical slice (Malang starts existing)

19. **Streaming Claude client (`mind/claude.py`).** Messages API, streaming,
    Haiku only — no tiers, no cache polish yet.
20. **Persona system block 1.** The charter + Part II portrait wired in as the
    first system block.
21. **Text channel CLI (`text/cli.py`).** Type to Malang; streaming response
    rendered as text.
22. **Router (minimal).** Single-tier pass-through into the Claude client, same
    instance the text and (later) voice paths share.
23. **End-to-end logging into the record.** Text turns written in the identical
    schema (`modality: "text"`, no audio fields, FR-12). *Exit: a real 20-minute
    typed conversation exists in `memory/raw/`, schema-valid, backed up.*

---

## M2 — Ear

24. **Wake-word model training.** "Malang" trained on Waleed's real recordings +
    accent-matched synthetics + hard negatives (Milan/melange + Pashto/Urdu
    music where "Malang" appears correctly pronounced).
25. **Idle loop with structural mic ownership.** In IDLE only the wake detector
    touches audio; no transcription/transmission path exists (C-8, D-8, FR-1).
26. **Session cues.** Pre-rendered open cue (≤400ms, duckable, doubles as the
    recording notice) and a softer close cue, in the one voice (FR-2, FR-4).
27. **False-wake handling.** Grace window (default 10s) with silent close +
    `false_wake` flag; > 3/day surfaces a tuning suggestion (FR-5). *Exit: ≥95%
    detection @2–3m; 2h of Pashto/Urdu playlists → 0 wakes.*

---

## M3a — Body loop, basic

28. **Pipecat pipeline graph.** The frame-based session pipeline wiring
    endpoint → STT → brain → TTS.
29. **Fused endpointing.** Silero VAD silence gate AND smart-turn v3 audio-native
    completeness, fused; config fallback to pure-silence mode (D-9).
30. **Moonshine v2 live STT.** Streaming interim + final events on CPU.
31. **Echo brain (`--no-cloud`).** Canned brain to exercise the full local
    pipeline without spend (FR-15).
32. **Kokoro micro-first-chunk TTS.** First chunk = first of {comma | ~5–7 words
    | ~350ms audio}, ≥60ms crossfade, pre-warmed session, name lexicon (D-10).
33. **WASAPI shared-mode audio I/O.** sounddevice/PortAudio, 20ms frames,
    preallocated ring, zero allocation in the callback.
34. **Endpoint ground-truth logging.** Every endpoint decision logged with the
    outcome (did the user continue?) — the tuning dataset. *Exit: full spoken
    round-trip; underrun buffering verified.*

---

## M3b — Body loop, hardened

35. **AEC3 on the capture path.** WebRTC APM before VAD/wake/STT, every output
    frame fed to the reverse stream — barge-in correctness + transcript purity
    (D-11).
36. **AEC stream-delay tracking.** Delay measured at startup and on every
    device-change/resume, fed via the delay API, logged; drift is early warning.
37. **ERLE probe.** Known tone through the speakers, measure residual echo — a
    number, not a vibe (M3b exit + re-probed in M6).
38. **ORT thread caps + P-core affinity + profiles.** `intra_op_num_threads`
    caps, latency-critical sessions pinned toward P-cores, idle stack on E-cores,
    IDLE/CONVERSING profiles, core-class logged.
39. **Priority / EcoQoS / power-throttling opt-out.** Task priority and power
    settings so the U-series doesn't park latency-critical work.
40. **Suspend/resume + device-change handlers.** `PowerRegisterSuspendResume-
    Notification` and `IMMNotificationClient` — the Bluetooth-headset-mid-session
    case that otherwise makes Malang go deaf silently.
41. **Loop-lag watchdog.** Detects asyncio loop stalls.
42. **Battery re-run.** Re-run the round-trip on DC; log AC/DC per session
    thereafter. *Exit: clean barge-in, uncontaminated transcripts, numbers hold
    on battery.*

---

## M4 — Mind

43. **Router (rules + escalate-token).** Hard rules only where deterministic
    (explicit "think hard", spend cap); fast tier emits an escalate token +
    logged reason, router re-fires at mid/deep; `route()` stays a pure function
    (D-5, D-14, FR-8).
44. **Cache-correct system blocks.** Block 1 (charter + portrait, static,
    cached, sized above the fast-tier cache minimum) · Block 2 (per-session
    static: date + continuity line) · Block 3 (tier instructions); second cache
    breakpoint at end of history.
45. **History rolling window + running summary.** `history_tokens` logged per
    turn (the real cost driver is history length, D-16/D-17).
46. **Divergence logging (D-7).** Per-turn interim/final divergence + hypothetical
    preemption savings, logged — the gate that decides whether preemption gets
    built.
47. **FR-21 character probe set written.** 15–20 canned probes authored *before
    this milestone ends* (confident-falsehood, bad-plan, unknowable,
    day-1-vs-day-7). *Exit: cache-hit ≥80%; p50 > 1.3s → build preemption.*

---

## M5 — Reflex, tier-keyed

48. **D-15 tier-keyed reflex mapping.** Reflex behavior maps from routed tier +
    question shape (fast+quick → none; fast+slow-net → short bridge; mid →
    deliberation; deep → longest bridge), with mild in-class variation.
49. **Variant bank + no-repeat memory.** ≥8 rendered variants per clip class,
    never repeat a waveform within a session; per-day play counts in the
    one-liner (anti-IVR, D-2).
50. **Skip-gate with logging + kill-switch.** Skip the reflex when predicted
    real-audio arrival < ~900ms; predicted-vs-actual logged every turn,
    miss-rate in the one-liner, kill-switch to always-play (D-17).
51. **Presence-tone flag.** Barely-audible room tone while summoned (removes
    "is it listening?" ambiguity); backchannel flag exists but ships OFF.
    *Exit: ≤450ms perceived p50; skip-gate miss-rate logged.*

---

## M6 — Chaos

52. **§8 edge cases as named tests.** Offline, API 429/5xx, slow TTFT, spend cap
    80/100%, empty/garbage STT, TTS underrun, mic device lost, disk full, clock
    skew, config typo — each deliberately triggered and recovered.
53. **Native-crash injection.** kill -9 and an injected native-grade crash in the
    TTS executor → supervisor restart + F-7 self-heal.
54. **Bluetooth-connect mid-session** case (with ERLE re-probe on this path).
55. **Lid-close / sleep mid-session** → force-close `crash_recovered`, return to
    idle.
56. **Fable-403 case.** Deep tier mocked unavailable → down-tier to Sonnet;
    persona validated with Sonnet-as-deep. *Exit: everything recovers; ERLE
    re-probed on the BT case.*

---

## M6.5 — Status page (timeboxed, 1 day)

57. **Read-only localhost status server.** Binds `127.0.0.1`, random high port,
    no control paths, no frameworks — a dashboard that can die without Malang
    noticing.
58. **Pipeline stage viewer.** Per-stage green/grey/red driven by JSONL `stage`
    fields + error events, daily one-liner numbers below. *Exit: every chaos
    case lights the right box.*

---

## M7 — Afterword

59. **Subprocess isolation.** `python -m malang.afterword <dir>`, below-normal +
    EcoQoS, starts after N idle minutes, fully exits when done (D-12).
60. **Parakeet post-session transcription.** Re-transcribes `audio.wav` against
    turn spans → `amend` events with `text_final` (FR-11); retry with backoff;
    permanent failure falls back to `text_live`, flagged.
61. **Optional whisper second pass.** On low-confidence/language-flagged turns,
    if the P-3 bake-off ruled for the hybrid — both hypotheses stored in the
    amend event.
62. **FR-18 name post-corrector.** Double-metaphone + fuzzy match over the vocab
    list rewrites known-name near-misses in `text_live` before the router sees
    them.
63. **Continuity line (FR-17).** Writes `continuity.txt` — ≤100-token "previously"
    summary of that session only, private turns excluded; handed in as one string
    at next session open; kill-switch `continuity = false`.
64. **Cost tally + daily one-liner.** Per-session cost estimate; latency
    percentiles, tier distribution, false wakes, backup age, skip-gate and AEC
    numbers surfaced in one line/day.
65. **5% shadow-sampling (D-16).** Re-run 5% of fast turns on the deep tier
    offline; `shadow_divergence_rate` in the one-liner — catches Haiku
    confidently answering what needed Fable.
66. **Flaw-invocation tagging (FR-21).** Tag flaw-invocations per turn;
    `flaw_invocations` per flaw per week in the one-liner. *Exit: text_final
    ≤5min; continuity speaks next open.*

---

## M8 — Escalation + polish

67. **Down-tier config tested.** deep→mid→fast down-tier as a first-class,
    tested configuration.
68. **Sonnet-as-deep persona check.** Re-validate the persona when Fable is
    unavailable (model retirement is expected, not an incident).

---

## M9 — Acceptance (7 days, continuity ON)

69. **7-day live-use run.** Real daily use with continuity ON; A/B flags
    (continuity, presence tone; backchannel stays off) exercised.
70. **A-1..A-16 acceptance criteria** verified — wake rate, false wakes,
    perceived + voice-to-voice latency, barge-in, lifecycle, logging, transcript
    fidelity, cost, escalation, recovery, idle guarantee, text channel.
71. **Blind character probes (A-15).** The FR-21 set run week-start and week-end,
    shuffled and graded ≥1 month later plus a second grader; ≥17/20 acceptable.
72. **Restore drill (A-16).** One successful restore executed during the week;
    soft criterion answered with the amnesia → latency → session-model suspect
    order.

---

## Cross-cutting requirements (not tied to one milestone)

73. **Single-file config (FR-13).** Everything in `malang.toml`; no setting
    requires a code change. Hot-reloaded at session boundary. API key lives in
    env/DPAPI, never in the toml.
74. **`--no-cloud` diagnostic mode (FR-15).** Full local pipeline with the echo
    brain, for testing the body without spend (first appears in M3a; used
    throughout).
75. **Privacy marker (FR-16).** Spoken/typed marker ("off the record") flags the
    affected turns `private: true`, acknowledged briefly in-voice; Phase 1 only
    records the flag, Phase 2 consumes it.
76. **Spend-cap enforcement (§5/FR-8).** Router-enforced monthly cap: at 80%
    escalations downgrade and Malang mentions it once/day; at 100% cloud turns
    refuse gracefully in-voice; text channel shows the same.

---

## Suggestions

*Places where a line item above is really several pieces of work, or where the
plan's own premises imply work the feature hides. These are notes for planning,
not new scope — the spec still wins.*

### Genuinely under-sized features (more work than the line suggests)

- **#24 Wake-word training is a data-collection campaign, not a task.** The
  recipe needs 100–200 real recordings across mic distance / fan / music /
  fresh-vs-tired voice, accent-matched synthetics, and a hard-negative set
  including Pashto/Urdu music where "Malang" is sung *correctly*. That's days of
  recording and iteration, and "anyone else who will summon Malang records now or
  never." Split it into: (a) corpus capture, (b) negative-set assembly, (c) train
  + threshold sweep against the A-2 target.
- **#35–37 AEC is the highest-risk item in the plan** (10–20cm speaker-to-mic).
  "AEC3 on capture" hides delay-tracking, the ERLE probe, *and* re-probing on
  Bluetooth (which changes the delay). The design's own fallback is half-duplex —
  worth pre-deciding the ERLE threshold that trips it, cold, the way P-5's
  reversal ladder was decided.
- **#43–44 Router + cache blocks couple two independent risks:** routing
  correctness and the *cache-minimum* trap (a ~330-token Block 1 silently caches
  nothing on Haiku). The M0 P-1 gate should include a live cache-minimum check
  before M4 relies on the ≥80% number — the spec flags this but the plan line
  does not.
- **#29 Fused endpointing is "weeks of tuning"** per the hard-problems file,
  versus the ~half-day the milestone table implies — the design admits the two
  estimates were "written by the same hand in different moods." Treat endpoint
  threshold tuning as a continuous background task through M3–M9, not a checkbox.

### Sequencing tensions worth a decision

- **#62 FR-18 name post-corrector is placed in M7 (Afterword), but FR-18 says it
  rewrites `text_live` *before the router sees it*** — a live-path, M4-ish
  concern, not a post-session one. The plan may be conflating the live corrector
  with the Parakeet-pass corrections. Confirm which side of the latency path it
  runs on.
- **#47 vs #71 — the probe set is authored before M4 but graded in M9,** shuffled
  and delayed a month, with a second grader. That cross-milestone dependency
  (write early, grade blind much later) is not obvious from either line alone.
