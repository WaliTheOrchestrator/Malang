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

## P-3 - STT bake-off: Moonshine / Parakeet / whisper-turbo, code-switched (pending)

## P-4 - Selective-int8 Kokoro ear check + WASAPI buffer probe (pending)

## P-5 - Sustained 10-minute duplex load, mains and battery, core-class logged (pending)

## P-6 - Blind voice selection across Kokoro voices (pending)
