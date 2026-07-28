---
name: measure
description: Run a Malang measurement gate (P-1 through P-6) honestly and record its ruling. Use for M0, for any re-measurement after a hardware or model change, and whenever a number in spec section 5 is being relied on but has never actually been measured on the machine.
---

# Run a measurement gate

The project's rule: **every acceptance carries a measurement gate; every
rejection names the gate that reverses it.** A gate that is run sloppily, or
run once and never again, converts that discipline into decoration.

## The gates

| Gate | Measures | Ruling it produces |
|---|---|---|
| P-1 | Claude API TTFT from this ISP, morning and evening, n≥20 | whether the reflex tier is optional or mandatory-first |
| P-2 | Kokoro RTF on this laptop, sustained | Kokoro confirmed, or the fallback ladder opens |
| P-3 | STT bake-off: Moonshine small/medium, Parakeet, whisper-turbo, on a code-switched passage; WER + proper-noun error rate | which STT ships, and whether a second pass is needed |
| P-4 | Selective-int8 Kokoro, blind A/B by ear, plus the WASAPI buffer probe | int8 or fp32; the negotiated buffer size |
| P-5 | Sustained 10-minute duplex load, full stack resident, minute 1 vs minute 10, mains and battery, core-class logged | whether §5's budgets survive this chassis — the decisive gate |
| P-6 | Blind voice selection across Kokoro voices | the one voice, baked into `render_reflexes.py` |

## Protocol

1. **Write the script first, into `scripts/measure_<gate>.py`.** A measurement
   you cannot re-run is an anecdote. It must be repeatable after a Windows
   update, a driver change, or a model swap.
2. **State the conditions in the output**: AC or battery, background load, room,
   mic, time of day, and for P-5 the core class each ORT session landed on.
3. **Report percentiles, not means.** p50 and p95. The worst turns are what
   presence is judged by.
4. **Run it on the real machine, with the real mic, in the real room.** Bench
   numbers and simulated audio will lie to you — this is written into the
   hard-problems document as the rule of thumb across all of them.
5. **Record the ruling in `docs/m0-measurements.md`**, in this shape:

```
GATE: P-x
DATE / CONDITIONS:
RAW NUMBERS:
RULING:            (which branch of the gate fired)
CONSEQUENCE:       (what in the spec this changes, by section)
REVERSED BY:       (what future measurement would change this ruling)
```

6. **If the gate fails, take its named reversal.** They are pre-decided cold,
   on purpose, so that a bad number is a branch and not a crisis. P-5's ladder:
   1.5–2.0s → re-baseline; 2.0–2.5s → Supertonic replaces Kokoro; >2.5s → voice
   becomes a mode and the text channel is the daily driver.

## The failure to avoid

Do not report a number the pipeline never actually produced. Do not average away
a bad run. Do not measure on mains and present it as the budget. The project has
twice re-baselined honestly rather than defend a stale figure, and that is the
reason its documents are worth anything.
