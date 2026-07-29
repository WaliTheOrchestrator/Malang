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

**STATUS: READY TO RUN.** P-2 is fully local and free - no API key, no network - so it is
the first M0 gate that can be run to a recorded ruling. Probe:
`scripts/measure_p2_kokoro.py` (self-contained; `kokoro-onnx` lazily imported).

Setup once: pin the `uv` venv to **Python 3.12** (NOT the system 3.14 - `kokoro-onnx`
requires `<3.14`); `uv add kokoro-onnx`; download `kokoro-v1.0.onnx` and
`voices-v1.0.bin` from the `model-files-v1.0` release into `models/`.

Run BOTH power sources, then paste each block below and write the ruling.
Gate (spec section 9): **aggregate p50 RTF < 0.8 sustained -> Kokoro confirmed**; else the
fallback ladder opens (quantized ONNX -> Supertonic 3 -> Piper).

```
GATE: P-2
DATE / CONDITIONS:   <fill: mains run - timestamp, i3-1315U>
RAW NUMBERS:         <paste the script's block: aggregate RTF p50/p95, per-length
                      breakdown, round1-vs-roundN drift, core-class, non-silence guard>
RULING:              PENDING (mains run not yet pasted)
CONSEQUENCE:         spec section 5 active-session CPU/"fan behavior"; feeds (does NOT
                     equal) the 300ms TTS-first-audio budget - that is HP16 / M3a
REVERSED BY:         a re-run crossing 0.8 the other way (quantized/fp16 build, thermal
                     state, model swap, or the battery run)
```

```
GATE: P-2
DATE / CONDITIONS:   <fill: battery run - timestamp, i3-1315U>
RAW NUMBERS:         <paste the script's block>
RULING:              PENDING (battery run not yet pasted; spec section 4 P-4 makes this
                     run mandatory - a mains-only ruling is "fiction for a laptop")
CONSEQUENCE:         spec section 5
REVERSED BY:         a re-run crossing 0.8 the other way
```

---

## P-3 - STT bake-off: Moonshine / Parakeet / whisper-turbo, code-switched (pending)

## P-4 - Selective-int8 Kokoro ear check + WASAPI buffer probe (pending)

## P-5 - Sustained 10-minute duplex load, mains and battery, core-class logged (pending)

## P-6 - Blind voice selection across Kokoro voices (pending)
