# P-2 — Kokoro RTF measurement

**Milestone:** M0 · **Branch:** `feat/p-2-kokoro-rtf-measurement` · **Created:** 2026-07-29
**Spec version:** 1.0 · **Status:** done
**Governing docs:** malang-phase1-spec.md §9 (P-2), §5 (resource + latency budget), §4 (TTS decision), §4 P-4 (battery re-run) · design §2 (TTS stack), §6 (module layout), §7 (M0 exit, risks), §4 D-4/D-10 · hard-problems HP16 (first-chunk ≠ RTF), HP13 (int8 drift — out of scope here)

---

## 1. Overview

P-2 is the second measurement gate: it measures **Kokoro-82M's real-time factor (RTF) on the actual laptop** — the ratio of synthesis wall-time to the duration of audio produced. RTF is the single number that decides whether Kokoro can be Malang's voice on this CPU at all, or whether the pre-decided fallback ladder (quantized/ONNX Kokoro → Supertonic 3 → Piper) has to start. Every §5 line that assumes Kokoro (the TTS-first-audio budget, the "fan behavior stays acceptable" active-session claim, the whole one-voice identity) is an assumption until this gate rules. Unlike P-1, P-2 needs no API key and no network — it is fully local and free, so it can run today. It is a hand-run script, not a runtime module and not a pytest test.

## 2. Governing requirements

| Source | Requirement (quoted) |
|---|---|
| §9 P-2 | "Kokoro-82M RTF on the actual laptop (synthesize 10 varied sentences, measure)" |
| §9 P-2 gate | "RTF < 0.8 sustained → Kokoro confirmed. Else: test ONNX/quantized Kokoro first; Piper is the last-resort fallback (accepting the voice-quality loss consciously, not silently)." |
| §5 | "Kokoro RTF must measure <0.8 on the actual machine (see §9)." |
| §5 | "Active session: sustained CPU such that fan behavior stays acceptable" |
| §4 P-4 | "v1.2: repeat P-2 and the M3 round-trip ON BATTERY — a budget validated only on mains is fiction for a laptop; log AC/DC per session thereafter." |
| §4 TTS | "Fallback order (v1.2): Supertonic 3 before Piper (much smaller quality gap)." |
| design §7 M0 exit | "P-1/P-2/P-3/P-4 gates pass (spec §9) … numbers in appendix" |
| design risk | "Kokoro too slow on this CPU \| P-2 RTF ≥ 0.8 \| Quantized/ONNX build first; Piper as conscious last resort (D-4 note)." |
| HP16 | "Kokoro synthesizes an entire chunk before the first sample exists … per-call overhead makes tiny texts *relatively* slower (RTF ~0.7 on short strings vs ~0.5 on long)." — so the corpus MUST vary sentence length, and RTF is **not** first-audio latency. |
| CLAUDE.md | "Prefer a ten-line script and a stopwatch over an argument about a number." |
| CLAUDE.md | "Say what you actually measured, not what should happen." Record the ruling. |
| C-2 | "CPU-only local inference (no dGPU available)." |

## 3. Depends on

- **Specs / milestones:** none upstream. P-2 is independent of P-1 — it touches no cloud, needs no `ANTHROPIC_API_KEY`, and is not blocked by P-1 being DEFERRED. Because it is fully local and free, **P-2 is the first M0 gate that can be run to a recorded ruling** — P-1 is built but held open for want of an Anthropic key, so the M0 appendix is still empty. Ruling P-2 does **not** close M0: the exit test needs P-1/P-3/P-4 too (P-5/P-6 also pending). P-2 gates the TTS decision for M3a and everything downstream that assumes Kokoro's voice.
- **Measurement gates:** this **is** a gate. No gate precedes it. It partially overlaps P-4 (selective-int8) and P-6 (voice identity), both of which are **out of scope** here (§16).
- **Hardware / environment:** the reference **i3-1315U**, **mains AND battery** (§4 P-4 makes the battery run mandatory — a mains-only number is "fiction for a laptop"). Built-in audio not required (RTF is measured from synthesis timing + sample count, not from acoustic playback). No mic, no network.

## 5. Log schema impact

**None.** The probe writes only to `docs/m0-measurements.md` and an optional CSV in the scratch tree. It writes nothing under `memory/raw/` and touches no session log. (No §4 Contract entry: P-2 defines no §6.3 module boundary — `speech/tts.py` will formalize the `TTS` contract at M3a; this script only times raw synthesis.)

## 6. Latency and resource budget

P-2 measures a resource property that feeds — but is not identical to — the §5 TTS stage:

| §5 stage | Budget p50 | Ceiling p95 |
|---|---|---|
| TTS first audio of first micro-chunk (selective-int8 Kokoro, ≤7 words) | 300ms | 450ms |

**Flag (bold, per the rules): RTF is not the 300ms first-audio number.** HP16 is explicit that the first micro-chunk's wall-time — not full-sentence RTF — is what the reflex tier races. A sustained RTF < 0.8 is necessary but **not sufficient** for the 300ms budget; first-audio latency is measured properly at M3a with the real micro-first-chunk pipeline (D-10), not here. P-2's own gate is purely `RTF < 0.8 sustained`. CPU/RAM footprint: one ORT session, `intra_op_num_threads` per the design's start value (2–3), well inside the 2GB reservation; state the thread count used in the output.

## 7. Config keys

The probe is a hand-run measurement script, so its knobs are **CLI arguments with defaults**, not `malang.toml` settings (FR-13 governs *runtime* config; a one-off script is not runtime). Documented defaults:

```
--rounds        5                 # times the 10-sentence corpus is synthesized; "sustained" = many, not one warm call
--voice         af_heart          # §6.4 default; voice IDENTITY is P-6's call, not P-2's — RTF is ~voice-independent
--threads       3                 # ORT intra_op_num_threads (design §2 start value for Kokoro)
--build         standard          # standard | quantized — the fallback ladder's first rung is measured with quantized
--label         mains|battery     # REQUIRED framing; a run with no power label is not a valid P-2 record (§4 P-4)
--dry-run       (flag)            # offline; exercises the report + ruling on synthetic numbers, imports no TTS engine
```

No kill-switch: hard rule 5 governs *probabilistic runtime components*; P-2 is a measurement, so it does not apply (same reasoning the P-1 spec recorded). The switch that matters is the fallback ladder in §12, keyed off the measured number.

## 9. Files to create

| Path | Purpose |
|---|---|
| `scripts/measure_p2_kokoro.py` | The probe (design §6 names it). Synthesizes the varied corpus `--rounds` times, computes per-sentence and aggregate RTF, prints the `/measure` ruling block. Pure core (corpus, RTF math, gate branches, formatter, local `percentiles`) is import-clean; the Kokoro import is **lazy** (inside the synthesis layer) so the pure core, `--dry-run`, and the unit tests need nothing installed — exactly the P-1 pattern. |
| `tests/test_measure_p2_kokoro.py` | Unit tests for the pure core only (RTF computation, gate branches, arg parse, corpus length-variance, percentiles, `--dry-run` smoke). No engine, no audio. |
| `pyproject.toml` | **Created fresh** — absent on this branch (P-1's copy is unmerged). Project metadata, `requires-python >=3.12,<3.14` (the kokoro-onnx ceiling, §11), `kokoro-onnx` dep, `pytest` dev dep. |
| `tests/conftest.py` | **Created fresh** — puts `scripts/` on `sys.path` so the pure core is importable by the tests. |
| `docs/m0-measurements.md` | **Created fresh** — absent here; the M0 appendix with the P-2 section (and pending stubs for the other gates). |

## 10. Files to change

| Path | Change | Risk |
|---|---|---|
| `Phase 1/malang-phase1-plan.md` | Tick the P-2 item of the M0 checklist once ruled | none — doc |

(`docs/m0-measurements.md`, `pyproject.toml`, and `tests/conftest.py` are **created**, not changed — see §9; they are absent on this branch because P-1 is unmerged.)

## 11. New dependencies

| Package | Version | Why | CPU-only? | Windows? | License |
|---|---|---|---|---|---|
| `kokoro-onnx` | `0.5.0` (pin at install) | Runs Kokoro-82M via onnxruntime on CPU — matches design §2's "selective-int8 **ONNX**" framing; the measurement engine for RTF. Import name `kokoro_onnx`. | **yes** — pulls `onnxruntime>=1.20.1` (CPU) as a hard dep; GPU only via the opt-in `[gpu]` extra, which we do **not** take | **yes** — bundles `espeakng-loader` (ships a `win_amd64` wheel), so no separate espeak-ng install | **MIT** (wrapper) |

Verified by `docs-researcher` against PyPI + the GitHub source, 2026-07-29 (confidence: confirmed unless noted):

- **Two licenses, both clean:** the `kokoro-onnx` wrapper is **MIT**; the Kokoro-82M **model weights** are **Apache-2.0** (hexgrad HF card). No conflict. (Note: PyPI's `license` metadata field is empty — the MIT declaration lives only in the repo `LICENSE`, so any compliance tooling that scans PyPI classifiers will see nothing; check the repo, not PyPI.)
- **Model + voices are a MANUAL download**, not bundled and not auto-fetched by the library. The constructor takes explicit paths: `Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")`. Release `model-files-v1.0` assets, URL pattern `https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/<file>`:
  - `--build standard` → `kokoro-v1.0.onnx` (f32, ~310 MB) — the baseline the gate is written against
  - `--build quantized` → `kokoro-v1.0.int8.onnx` (int8, ~88 MB) — the first fallback rung (its *quality* is P-4, not P-2)
  - `kokoro-v1.0.fp16.onnx` (~169 MB) also exists as a future third tier, not wired to a flag now
  - `voices-v1.0.bin` — 26 voices, includes the `af_heart` default
  The script should download these once (scripted `curl`) and point at the files directly — no Pipecat resampling in the measurement path.
- **`--build` maps cleanly** to swapping the model-file path against the same constructor — no code-path fork. The **selective-int8 build itself remains a P-4 quality artifact**; P-2 only times it.
- **Python version constraint — action required:** `kokoro-onnx` requires **`>=3.10,<3.14`**. The machine's system `python` is **3.14.3**, *outside* that range — a naive `pip install` against the system interpreter fails loudly at resolution time. The `uv`-managed venv MUST be pinned to **3.12** (the CLAUDE.md convention) before install. Verify the active interpreter is 3.12, not 3.14, as the first implementation step.

Like `anthropic` for P-1, this dep is needed anyway by `speech/tts.py` at M3a, so P-2 introduces nothing the project wasn't already taking.

## 12. Rules for implementation

Hard rules that bite here: **the working-style rule** (measure, don't assume; record the ruling; a missing run is honest, a zero is a lie) and **C-2** (CPU-only). Then:

1. **Measure RTF honestly.** `RTF = synthesis_wall_time / output_audio_duration_seconds`, where audio duration = `n_samples / sample_rate`. **Read `sample_rate` from the engine's actual output, never hardcode it** — `kokoro.create(text, voice)` returns `(samples, sample_rate)`, so consuming the returned rate is trivial (it is 24 kHz today; a wrong hardcoded constant would silently scale every RTF and the gate would rule on a lie). Time only the synthesis call — **exclude** model load and the pre-warm dummy synthesis (D-10: the ORT session is pre-warmed at load; a cold first call is not the production number). Set `trim` **explicitly** and record its value: `create()` defaults to `trim=True`, which strips leading/trailing silence and so shrinks the denominator (raising RTF) — whatever you choose, it must be identical across every round and both power labels, and stated in the ruling. RTF < 1.0 means faster than real-time; the gate is < 0.8 sustained.
2. **Guard against silent synthesis on EVERY call — the one failure that would make every RTF a lie.** The bundled espeak-ng path in this package family has produced *empty/silent audio with no exception* on Windows (`docs-researcher`, 2026-07-29; observed on non-English voices, English unproven but not cleared). RTF computed over silence is a meaningless number that looks like a pass — and a *full-length but silent* clip computes a perfectly normal-looking RTF, so a guard scoped to the warm-up call alone is not enough (both reviewers flagged this). Check the peak amplitude (`|samples|.max() > floor`) on the warm-up **and on every measured synthesis**; on the first silent/empty clip, abort the whole run loudly and record nothing — one silent synthesis makes every RTF after it untrustworthy. A cheap guard; it is exactly the silent-degrade class this project is built to catch.
3. **"Sustained" is not one warm call.** Synthesize the full 10-sentence corpus `--rounds` times. Report aggregate **p50 and p95** RTF (never a mean — the §5 house rule), and separately report **round-1 vs round-N drift** as the thermal early-warning: the U-series chassis throttles by minute 3–10 (§5), and a number that only holds for ten seconds is not "sustained." (Full-stack sustained load under AEC+STT+recorder is **P-5's** job, not P-2's — here it is Kokoro alone.) **Log the observed core class** the ORT session actually ran on (P/E) if cheap to read — design §2 warns the Windows Thread Director will park Kokoro on E-cores at whim, making the number non-reproducible; full P-core affinity pinning is P-5's mechanism, but if the RTF looks scheduler-dependent here, that is itself a finding for the ruling.
4. **Vary the corpus by length, and fix it.** HP16: short strings carry per-call overhead and score *worse* RTF than long ones. The 10 sentences MUST span short (≤5 words), medium, and long (>25 words), so the ruling reflects the real distribution, not a flattering long-sentence average. Include one line with "Malang" and a family name for realism — but **grade speed only**; pronunciation correctness is P-4/P-6. The corpus is a **fixed constant in the script** (deterministic, like P-1's `build_prefix`), reused byte-identical across every round and both power labels — mains-vs-battery and round-1-vs-round-N are only comparable on identical inputs.
5. **Mains AND battery, labelled.** Run once on each; `--label` is required in the record. §4 P-4 makes the battery run mandatory. State power, thread count, and `--build` in the output.
6. **Report p50 and p95, the drift, and the per-length breakdown — and define which number the gate reads.** The gate reads **aggregate p50 RTF across the varied corpus < 0.8 sustained**. But the ruling MUST *also* break RTF out by length band (short / medium / long), because a passing aggregate p50 can hide a slow short-string tail (HP16) — and short strings are exactly what the first-chunk/reflex path will later race. A ruling that reports only the aggregate has thrown away the one number HP16 says will bite. The gate is sustained, so the p95 and the round-N number matter as much as p50.
7. **This is not a test.** It lives in `scripts/`, is run by hand, and loads a real model on purpose. It must never be collected by pytest — the pure helpers are what the unit tests import (the fresh `tests/conftest.py` puts `scripts/` on `sys.path`), and the engine import stays lazy so collection touches no ONNX runtime.
8. **Define `percentiles` locally — do NOT import from P-1.** This branch was cut from clean `main`; `scripts/measure_p1_rtt.py` lives only on the held-open, unmerged P-1 branch and is absent here. P-2 is self-contained: its own nearest-rank `percentiles` (a dozen lines) with its own table-driven test. When P-1 lands, the two copies converge in a trivial merge — coupling P-2 to unmerged work would be the worse trade.

## 13. Failure modes

| Case | Behaviour |
|---|---|
| RTF ≥ 0.8 sustained (`--build standard`) | Gate fails for base Kokoro. Pre-decided ladder (§9 + design §2/§4/D-4): re-run with `--build quantized`; if still ≥ 0.8 → **Supertonic 3** audition (design's "Supertonic 3 before Piper"); if that also fails → **Piper**, last resort, voice-quality loss recorded consciously in the ruling. Record which rung the voice landed on. |
| Round-N RTF drifts up >15% from round-1 | Thermal throttling is real on this chassis. Record it; note it foreshadows the P-5 sustained-duplex risk and may push the reversal ladder even if p50 looked fine cold. |
| Synthesis returns silent / empty audio (espeak-ng path bug — no exception raised), on warm-up **or mid-run** | Rule 2's non-silence guard checks every synthesis, not just the first: on the first silent/empty clip the whole run aborts loudly and records nothing. RTF over silence — including a full-length silent clip that computes a normal-looking RTF — would masquerade as a pass; this is the failure the guard exists to catch. |
| Model/voices file missing or engine import fails | Fail loudly with the setup path; record nothing (a missing run is honest, a zero is a lie). `--dry-run` still works offline. |
| `pip install` fails at resolution (wrong interpreter) | `kokoro-onnx` requires Python `>=3.10,<3.14`; the system interpreter is 3.14.3. Fails loudly, not silently. Pin the `uv` venv to 3.12 first (§11). |
| Battery run absent | The P-2 record is incomplete per §4 P-4 — a mains-only ruling is explicitly "fiction for a laptop." Do not mark the gate ruled until both labels exist. |

## 14. Test plan

- **Unit (pure core only, no engine, no audio):** RTF computation on known wall-time/duration pairs; gate-branch selection (< 0.8 confirmed / ≥ 0.8 fallback); arg-parse defaults + overrides; corpus spans the required length range; `--dry-run` exits 0 and prints a ruling block without importing the engine.
- **Contract:** none (no §6.3 interface — that arrives with `speech/tts.py` at M3a).
- **Pipeline harness:** none (P-2 times raw synthesis, not the Pipecat graph).
- **Manual:** the measurement itself. Numbered:
  1. Confirm the `uv` venv is Python **3.12** (not the system 3.14 — §11); install `kokoro-onnx`; download `kokoro-v1.0.onnx` + `voices-v1.0.bin` from the `model-files-v1.0` release. Confirm mains power.
  2. `python scripts/measure_p2_kokoro.py --label mains` → expect the non-silence guard to pass, then per-length + aggregate RTF p50/p95 and the round-1-vs-round-N drift.
  3. Unplug; `python scripts/measure_p2_kokoro.py --label battery`.
  4. Paste both blocks into `docs/m0-measurements.md` with the gate ruling, the per-length breakdown, and the rung the voice landed on.

No test writes under `memory/raw/`. No test calls the Claude API. No test imports the TTS engine.

## 15. Definition of done

- [ ] Milestone exit test (design §7 M0): **P-2 gate ruled and recorded** — quote the observed **aggregate RTF p50 and p95**, the **per-length-band breakdown** (short/medium/long — HP16), the round-1-vs-round-N drift, observed core class, `--rounds`, thread count, `--build`, and the **mains AND battery** split
- [ ] `python .claude/hooks/invariant_lint.py --full` clean
- [ ] `pytest -q` green (RTF + gate-branch + arg-parse + corpus unit tests; no engine, no network)
- [ ] No session written by this code (it writes none) — schema check trivially holds
- [ ] `spec-guardian` run; BLOCKING findings resolved
- [ ] `latency-auditor` run — P-2 feeds (but does not equal) the §5 TTS-first-audio budget; the RTF-vs-first-audio distinction is exactly what it audits
- [ ] `security-review` — trivially clean (no credentials, no egress, no subprocess; local synthesis only)
- [ ] P-2 ruling written into `docs/m0-measurements.md`, including which fallback rung (if any) the voice landed on
- [ ] Probe defaults documented in `--help`; no setting in any tracked runtime file
- [ ] **Usable that evening** — trivially met; the probe leaves the system untouched
- [ ] Build-plan P-2 checkbox ticked; M0 note written

## 16. Out of scope

- **The selective-int8 ear check (P-4).** P-2 grades *speed*; whether int8 sounds indistinguishable from fp32 (blind A/B, including "Malang" and family names) is P-4. P-2 may measure int8 *speed* as the `--build quantized` fallback rung, but never judges its quality.
- **First-audio / micro-first-chunk latency (M3a, D-10).** The 300ms first-chunk budget the reflex tier races is measured with the real micro-chunk pipeline, not from full-sentence RTF. This is the single most-likely misread of P-2 — HP16 names it.
- **Voice identity selection (P-6).** Which Kokoro voice becomes Malang is a separate blind-ranked gate; P-2 uses a config default and grades speed only.
- **Name/lexicon correctness (P-4/P-6).** The misaki custom-lexicon overrides for "Malang" and family names are a pronunciation concern, not an RTF one.
- **Sustained full-stack duplex load (P-5).** P-2 measures Kokoro alone; RTF drift under the whole resident stack (AEC + Silero + smart-turn + Moonshine + recorder + fsyncing Scribe) is P-5, the decisive gate on this hardware.
- Anything that reads from `memory/`.
