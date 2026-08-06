# M0 measurements

The measurement appendix (design section 8). Every number in spec section 5 is an
assumption until it appears here, measured on the reference machine (i3-1315U) in the
real room. Each gate is recorded in the `/measure` skill's shape:

```
GATE: P-x
DATE / CONDITIONS:
RAW NUMBERS:
RULING:            (which branch of the gate fired)
CONSEQUENCE:       (what in the spec this changes, by section)
REVERSED BY:       (what future measurement would change this ruling)
```

Rule of thumb: report p50 and p95, never a mean; state AC vs battery; run on the real
machine. Do not report a number the pipeline never produced (`/measure` skill).

> Note: this file was created on the `feat/p-2-kokoro-rtf-measurement` branch. The P-1
> ruling lives on the unmerged `feat/p-1-api-latency-probe` branch; when P-1 lands, its
> P-1 section merges in here. P-1 itself is DEFERRED (no Anthropic key yet).

---

## P-1 - Claude API network RTT + streamed TTFT

**STATUS: DEFERRED (on the P-1 branch).** No `ANTHROPIC_API_KEY` yet; the mind is on a
Groq stopgap. P-1 measures the *Claude* API, so it cannot be run against Groq without
fabricating the gate. See the P-1 branch and `docs/groq-latency.md` there.

---

## P-2 - Kokoro-82M RTF on the laptop

**STATUS: RULED - PASSED (mains AND battery), 2026-07-30.** Kokoro-82M (standard fp32
ONNX, `af_heart`, intra_op=3) is confirmed as Malang's voice. Aggregate p50 RTF **0.529
on mains / 0.555 on battery** - both well under the 0.8 gate. The fallback ladder stays
closed. Probe: `scripts/measure_p2_kokoro.py`, 5 rounds x the fixed 10-sentence corpus.

Gate (spec section 9): **aggregate p50 RTF < 0.8 sustained -> Kokoro confirmed.** Met on
both power sources.

```
GATE: P-2
DATE / CONDITIONS:   2026-07-30T10:12:38+05:00 | power=mains | machine=i3-1315U
                     build=standard | voice=af_heart | intra_op=3 | rounds=5
RAW NUMBERS:
    RTF aggregate  p50 0.529  p95 0.676   (n=50 syntheses)
    by length:     short p50 0.635 p95 0.731   medium p50 0.529 p95 0.603   long p50 0.485 p95 0.518
    drift:         round1 p50 0.484 -> roundN p50 0.589 (+21.8%)  <-- THERMAL DRIFT >15%
    elapsed:       129.8s over 5 rounds
    non-silence:   passed (warm peak 0.424; floor 0.01)
RULING:              Kokoro CONFIRMED (aggregate p50 0.529 < 0.8 sustained)
CONSEQUENCE:         spec section 5 active-session CPU/"fan behavior"; feeds (does NOT
                     equal) the 300ms TTS-first-audio budget - that is HP16 / M3a
REVERSED BY:         a re-run crossing 0.8 the other way (quantized/fp16 build, thermal
                     state, model swap)
```

```
GATE: P-2
DATE / CONDITIONS:   2026-07-30T10:16:01+05:00 | power=battery | machine=i3-1315U
                     build=standard | voice=af_heart | intra_op=3 | rounds=5
RAW NUMBERS:
    RTF aggregate  p50 0.555  p95 0.709   (n=50 syntheses)
    by length:     short p50 0.638 p95 0.722   medium p50 0.555 p95 0.610   long p50 0.504 p95 0.571
    drift:         round1 p50 0.509 -> roundN p50 0.555 (+9.0%)
    elapsed:       134.0s over 5 rounds
    non-silence:   passed (warm peak 0.424; floor 0.01)
RULING:              Kokoro CONFIRMED (aggregate p50 0.555 < 0.8 sustained)
CONSEQUENCE:         spec section 5
REVERSED BY:         a re-run crossing 0.8 the other way
```

**Ruling (both runs) - PASS, with two honest flags carried forward:**

- **Thermal drift is already real.** Mains drifted **+21.8%** (round1 p50 0.484 ->
  roundN 0.589) inside a ~2.2-min run that did NOT reach the minute-3-10 throttle window
  the U-series chassis is known for. Even the drifted roundN p50 (0.589) still clears 0.8,
  so the gate holds - but this is a yellow flag for **P-5** (the 10-min sustained duplex
  load), which is the real throttle test, not P-2. Battery drifted only +9.0% (likely
  already clock-capped, so less thermal headroom to lose).
- **Short strings are the tightest, exactly per HP16.** The short band carries per-call
  overhead: p95 **0.731** (mains) / 0.722 (battery) - the closest any number came to the
  0.8 line. Still under, but the margin on short utterances is smaller than the aggregate
  p50 suggests. And RTF is NOT the 300ms first-audio budget (HP16) - that is
  first-micro-chunk latency, measured at M3a.

---

## P-3 - STT bake-off: Moonshine / Parakeet / whisper-turbo, code-switched

**STATUS: RULED (first pass), 2026-08-02.** whisper-large-v3-turbo dominates on this
speaker's accented, name-dense, heavily code-switched speech - a straight-swap ruling,
NOT the Parakeet-solo the spec had assumed. Moonshine's live WER is far above the ~12%
tolerance, so downstream text-keyed thresholds need recalibration. All four models mangle
the speaker's proper nouns (67-100% name error) - the FR-18 name lexicon is load-bearing,
and its seed list was captured (kept local; see below).

**Corpus honesty:** ~4 min of speech (3 registers - monologue / read / code-switched -
465 reference words), scripted read, single speaker, production mic, silence-trimmed.
This is REDUCED from the spec's original 30-min target by owner decision (2026-08-02),
accepted as a directional first-pass. Small-sample: WERs have wide confidence intervals.
Also: the speaker sometimes realizes /f/ as /p/, so a subset of substitution "errors" are
faithful to pronunciation, not model failures (e.g. a name with /f/ heard with /p/).

```
GATE: P-3
DATE / CONDITIONS:   2026-08-02T15:01+05:00 | machine=i3-1315U | threads=3
                     corpus=~4min/465w (monologue+read+codeswitch), scripted, silence-trimmed
                     parakeet=onnx-asr+silero-VAD int8 | whisper=faster-whisper turbo int8 vad_filter
                     moonshine=small+medium en (streaming, non-stream decode)
RAW NUMBERS (WER / proper-noun-error-rate, micro-averaged):
    model            overall  read   monologue  codeswitch   PN(all)  PN(codeswitch)
    whisper-turbo     36.3%   20.7%    31.4%       60.3%       66.7%      78.6%
    parakeet          51.2%   22.1%    43.3%       93.9%       92.6%     100.0%
    moonshine-small   55.9%   22.1%    51.0%       99.2%       88.9%      92.9%
    moonshine-medium  62.2%   25.0%    44.3%      128.2%       85.2%     100.0%
MEMORY-PATH RULING:  whisper-SWAP - whisper-turbo dominates across the board
                     (code-switched proper-noun gap +21.4pp, overall WER gap +14.8pp vs
                     Parakeet). SUBJECT TO runtime viability: whisper-turbo must fit FR-11's
                     5-min post-session window + the Afterword ~3GB peak on this i3 - NOT yet
                     verified (whisper is the slowest CPU model). Confirm before wiring M7.
LIVE-PATH RULING:    Moonshine live WER 55.9% (small) >> 12% -> RECALIBRATE every text-keyed
                     threshold downstream (reflex selector, fused endpointer, router escalate,
                     HP2). Even on clean read English it is ~22%; the ~12% assumption does not
                     hold for this speaker without FR-18 name repair. Recommended size: small
                     (lower WER than medium here). This changes M3a/M5 calibration.
CONSEQUENCE:         M3a live model = Moonshine (small) but with the recalibration flag;
                     M7 memory path leans whisper-turbo (pending runtime check), not Parakeet-
                     solo; FR-18 name lexicon confirmed essential (seed captured).
REVERSED BY:         a fuller/longer/spontaneous corpus (this is ~4 min, scripted); a
                     whisper runtime-viability failure (would fall back to Parakeet-primary +
                     whisper second pass, or Parakeet-solo); a model swap.
```

**Seed vocab (FR-18):** every name was mis-heard in believable ways (e.g. the presence's own
name landed as madame / manang / melang / malank across models). The full near-miss list is in
`docs/p3-vocab-seed.txt`, which is **git-ignored** (it contains real personal names) along with
the filled `corpus/p3/reference/*.txt` and `corpus/p3/manifest.json` - owner chose to keep all
name-bearing artifacts local, off GitHub. The harness, schema, and this name-free ruling are tracked.

**Open item for M7:** measure whether whisper-large-v3-turbo transcribes a full session inside
FR-11's 5-minute window on the i3-1315U before committing to the swap.

## P-4 - Selective-int8 Kokoro ear check + WASAPI buffer probe

Two independent sub-gates, both RULED (2026-08-06). **P-4a (int8 ear check) - ship
fp32.** **P-4b (WASAPI buffer) - CONFIRMED 40.0ms, mains AND battery, built-in speaker.**

### P-4a - selective-int8 vs fp32, blind ABX by ear

**RULING: SHIP fp32 (owner decision, 2026-08-06).** Two blind ABX runs both failed
the negative control - the grader could not distinguish even the *blind* off-the-shelf
int8 from fp32, so per spec §12 rule 1 no "int8 indistinguishable" verdict is
trustworthy. A *sighted* headphones comparison confirmed a real but very slight
difference (the gear is not broken); the difference is simply below the threshold of
reliable *blind* ABX discrimination on this voice (af_heart, English). Rather than
force a pass, we take the spec's conservative branch (§9 "Failing → fp32 and revise
honestly"): fp32 ships. int8 is not needed for speed (P-2 passed on fp32); its only
value is the ~220MB RAM + thermal headroom for P-5, so the selective-int8 build is kept
(behind `speech.tts.model_build`) and **revisited at P-5** only if RAM/thermal pressure
is real.

```
GATE: P-4a (selective-int8 ear check, blind ABX)
DATE / CONDITIONS:   2026-08-06 | machine=i3-1315U | grader=waleed | voice=af_heart
                     threads=3 | trials/contrast=24 | headphones (run 2)
                     builds: fp32=7d5df8ecf7d4 selective=f57cb0c5b15e blind=6e742170d309
                     names file SHA256 52c626be0eac...877d8406 | non-silence guard passed
RAW NUMBERS (two blind runs, both NEGATIVE CONTROL FAILED):
    run 1 (mixed gear):  selective 12/24 (p=0.58)   blind-control 13/24 (p=0.42)
    run 2 (headphones):  selective 10/24 (p=0.85)   blind-control 11/24 (p=0.73)
    sighted A/B check:   a real but SLIGHT difference audible (instrument not broken)
    name pronunciation:  9/9 name-bearing clips correct across fp32/selective/blind
RULING:              SHIP fp32. Negative control failed twice -> per §12 rule 1 the
                     "indistinguishable" reading is not trustworthy; take §9's fp32
                     branch. The difference is below blind-ABX threshold on this voice.
CONSEQUENCE:         speech.tts.model_build = fp32 for M3a. Selective-int8 build kept
                     (docs/p4-int8-build.md) and REVISITED at P-5 if RAM/thermal needs
                     it. Names confirmed sayable (9/9) - the D-4 render_reflexes bake is
                     unblocked for whichever build ships. Voice-independent; re-run on
                     the P-6 winner (rule 4).
REVERSED BY:         P-5 showing real RAM/thermal pressure (would re-audition int8 with
                     a more sensitive instrument / 2nd grader), a model or voice swap.
```

### P-4b - shared-mode event-driven WASAPI output buffer

**RULING: CONFIRMED (≤50ms), mains AND battery.** The negotiated shared-mode latency on
the built-in Realtek speaker was **40.0ms on both power sources** - inside the §5 50ms
ceiling, ~10ms below it, and ~20ms above PortAudio's shared-mode floor (§6: modest, not
comfortable, headroom). **Device-selection honesty (HP8):** the Windows *default* WASAPI
output had flipped to a virtual device ('Speakers (GVAUDIO)') by the mains run, so the
mains number was re-taken **explicitly on the Realtek built-in (device #13)** to match
the battery run's device - a Bluetooth/USB/virtual device is a different measurement (§3).
Both the GVAUDIO default and the Realtek built-in negotiated 40.0ms.

```
GATE: P-4b (shared-mode event-driven WASAPI output buffer)
DATE / CONDITIONS:   2026-08-06 | machine=i3-1315U | device='Speaker (Realtek(R) Audio)'
                     host=Windows WASAPI | mode=shared/event-driven
                     samplerate=48000 (device mix rate) | frame_ms=20 | channels=1
RAW NUMBERS (Stream.latency, the NEGOTIATED value - HP14):
    battery:  40.0ms   <= 50ms gate
    mains:    40.0ms   <= 50ms gate   (re-taken on device #13 Realtek; the auto-default
                                       had flipped to a virtual 'GVAUDIO' device)
    PortAudio shared-mode floor ~20ms - headroom to the 50ms gate is modest (§6)
RULING:              CONFIRMED on mains AND battery (40.0ms <= 50ms). The §5 shared-mode
                     output-path budget holds on the built-in speaker.
CONSEQUENCE:         confirms the §5 shared-mode output-path budget M3a is graded
                     against; keeps audio.output.exclusive=false the default. This is the
                     driver buffer, NOT the acoustic path (HP10/M3b - M3a/M3b instrument
                     the end-to-end perceived number).
REVERSED BY:         a different output device (Bluetooth/USB/virtual negotiates its own
                     buffer), a driver update, or a re-run crossing 50ms the other way.
```

**Both sub-gates RULED (2026-08-06):** P-4a ships fp32; P-4b confirmed 40.0ms mains AND
battery. The P-4 M0 checkbox is TICKED.

## P-5 - Sustained 10-minute duplex load, mains and battery, core-class logged (pending)

## P-6 - Blind voice selection across Kokoro voices (pending)
