# P-3 — STT bake-off

**Milestone:** M0 · **Branch:** `feat/p-3-stt-bake-off` · **Created:** 2026-07-31
**Spec version:** 1.1 · **Status:** done (first-pass ruled 2026-08-02 — see `docs/m0-measurements.md`; whisper-swap, pending M7 runtime check)
**Governing docs:** malang-phase1-spec.md §9 (P-3), §4 (dual-path STT decision + "errors in memory poison Phase 2 forever"), §5 (live-STT-final budget, RAM reservation), §6.1 (schema: `alternates`, `amend`, `final_transcript`), §6.3 (STT-live / STT-final contracts), FR-11 (post-session Parakeet pass + window), FR-18 (name post-corrector + P-3 vocab list) · design §2 (STT stack), §6 (`speech/` layout), §7 (M0 exit, risks), D-3 (dual-path STT), D-12 (Afterword subprocess) · hard-problems HP2 (interim text feeds endpointing/reflex — live WER quality bites here)

---

## 1. Overview

P-3 is the third measurement gate: a **quantitative speech-to-text bake-off** on ~4 minutes of hand-corrected reference speech (reduced from a 30-min target by owner decision, 2026-08-02; a directional first-pass), measuring **WER and proper-noun-error-rate** across the four candidate configs — **Moonshine v2 (small AND medium)** for the live path, and **Parakeet TDT 0.6B v3** vs **faster-whisper large-v3-turbo (int8/CT2)** for the memory path. It settles two decisions the rest of the build assumes: (a) which model writes the **durable record** — Parakeet solo, or Parakeet primary + a whisper-turbo second pass on flagged turns — and (b) whether **Moonshine's live WER is inside the ~12% tolerance** that every downstream text-keyed threshold (the reflex selector, the fused endpointer, the router's escalate features) is calibrated against. It also produces the first artifact of the **FR-18 vocab list**: the specific proper-noun near-misses this speaker, on this mic, actually causes. The memory-path choice is not a latency call — it is a **record-fidelity** call: §4 states plainly that transcription errors in the conversation vanish in seconds while **errors in memory poison Phase 2 forever**. Like P-2, P-3 needs no API key and no network (after a one-time model download), so it can run today. It is a hand-run script over a hand-labelled corpus, not a runtime module and not a pytest test.

## 2. Governing requirements

| Source | Requirement (quoted) |
|---|---|
| §9 P-3 | "Quantitative STT bake-off (v1.2; corpus reduced to ~4 min for the first-pass ruling by owner decision 2026-08-02): ~4 min of natural speech (monologue + read passage + deliberately code-switched passage), hand-corrected reference; WER + proper-noun-error-rate for Moonshine v2 (small AND medium), Parakeet TDT v3, and faster-whisper large-v3-turbo (int8/CT2)" |
| §9 P-3 gate | "Rulings: Parakeet within noise of Whisper on the code-switched passage → Parakeet ships solo. Whisper dominates → straight swap. Material gap on code-switched/proper-noun spans only → Parakeet primary + whisper-turbo second pass on low-confidence/language-flagged turns (both hypotheses stored in the amend event, in the Afterword subprocess, within FR-11's window). If Moonshine live WER >~12%, recalibrate every text-keyed threshold downstream. Word errors seed the FR-18 vocab list." |
| §4 STT-live | "**Moonshine v2** (streaming) … CPU-first streaming design … English; interim + final events; custom-vocab list from P-3 measurement." |
| §4 STT-memory | "**Parakeet TDT 0.6B v3**, post-session batch … Best CPU-viable English WER (~6.3%), native punctuation, no silence hallucination. Runs off the latency path; its output becomes the durable record." |
| §4 anti-goal | "Transcription errors in memory poison Phase 2 forever; errors in conversation vanish in seconds." — so the memory-path choice is a record-fidelity decision, weighted above the live path. |
| FR-11 | "Within 5 minutes of session close, a background job SHALL re-transcribe session audio with Parakeet and write `text_final` … permanent failure falls back to `text_live` and flags `final_transcript: 'failed'`." — the hybrid second pass, if ruled, must fit **inside this 5-min window and the Afterword subprocess**. |
| FR-18 | "a phonetic post-corrector (double-metaphone + fuzzy match over the P-3 vocab list …) SHALL rewrite known-name near-misses in `text_live` … the vocab list is dead weight without this. The list grows from A-9 spot-check corrections." — P-3 **seeds** this list; wiring it is FR-18/M7. |
| §6.3 STT-live | "`STT-live: feed(pcm_chunk) → events: {interim, text, stability} \| {final, text}`" — an **existing** contract, implemented at M3a; P-3 does not define it. |
| §6.3 STT-final | "`STT-final: transcribe(wav_path, spans[]) → [{turn_id, text, confidence}]  # batch, post-session`" — the memory-path contract this gate's ruling chooses the implementation for. |
| §6.1 schema | The `amend` event and the `alternates:[{source:"whisper-large-v3-turbo", value, confidence}]` field **already exist** in schema v1.3 — the hybrid's storage hook is present; P-3 changes no schema. |
| design §7 M0 exit | "P-1/P-2/P-3/P-4 gates pass (spec §9); bake-off ruling recorded; numbers in appendix" |
| design risk / D-3 | "Dual-path STT (Moonshine live / Parakeet final) … Transcription errors in memory poison Phase 2 forever; errors in conversation vanish in seconds." |
| C-2 | "CPU-only local inference (no dGPU available)." |
| CLAUDE.md | "Prefer a ten-line script and a stopwatch over an argument about a number." / "Say what you actually measured, not what should happen." — record the ruling. |

## 3. Depends on

- **Specs / milestones:** none upstream in the pipeline. P-3 is independent of P-1 (no cloud, no key) and of P-2 (a different model class). Fully local and free after the model download, so — like P-2 — it can be **run to a recorded ruling now**. Ruling P-3 does **not** close M0: the exit test still needs P-4/P-5/P-6 (and P-1, DEFERRED). P-3 gates the **memory-path model** for M7 (Afterword/Parakeet job, and whether the whisper second pass is built at all), confirms the **live-path model + size** for M3a (Moonshine small vs medium), and seeds **FR-18** (post-corrector) and the **misaki lexicon** (P-4/P-6 both consume "the P-3 vocab list").
- **The corpus is the real dependency, and it is human labour, not a download.** P-3 needs **~4 min of the owner's own speech on the actual mic** (originally scoped at 30 min; reduced by owner decision 2026-08-02 for a first-pass ruling), spanning three deliberately different registers (monologue / read passage / code-switched), then **hand-corrected** into a ground-truth reference with **proper nouns tagged**. Without a faithful, representative reference there is no WER — a corpus with no real Urdu/Pashto↔English code-switching and no proper nouns would let every model "pass" on a flattering distribution (a §13 validity failure). This recording+labelling is the bulk of P-3's cost and cannot be shortcut.
- **Measurement gates:** this **is** a gate; none precedes it. It is an **accuracy** gate, not a latency one — Moonshine's live *latency* is M3a's job, not P-3's (§16).
- **Hardware / environment:** the reference **i3-1315U**, the **real mic** used in production (accent, room, and mic all shape WER — a corpus recorded on a different device is a different measurement). No speakers, no network at run time. CPU-only (C-2); large-v3-turbo and Parakeet are loaded **one at a time** to stay inside the 8GB / 2GB-reserved envelope.

## 4. Contracts

**No new contract.** P-3 defines no §6.3 boundary. It *evaluates candidate implementations of an existing one* — `STT-final: transcribe(wav_path, spans[]) → [{turn_id, text, confidence}]` — and confirms the live model behind `STT-live`. Those contracts are implemented at M7 and M3a respectively; the bake-off harness calls each engine's own API directly and does not honour the §6.3 shape (it is a measurement, not the module).

## 5. Log schema impact

**None.** The bake-off writes only to `docs/m0-measurements.md`, a seed vocab file, and optional CSVs in the scratch tree. It writes nothing under `memory/raw/` and touches no session log. Worth stating explicitly because the ruling *decides how an existing field is used later*: the `amend` event and the `alternates:[{source:"whisper-large-v3-turbo", …}]` field are **already in schema v1.3**, so even the hybrid ruling requires **no schema change** — it only determines whether M7 populates that already-present optional field. (If a future reading of the ruling ever seemed to need a *new* field or event, that would be a `schema-change`-skill task and, if it forced rewriting Phase 1 records, a C-7 violation to redesign as additive — but nothing here does.)

## 6. Latency and resource budget

P-3 grades **accuracy, not latency** — it deliberately does not time the models (that is M3a for the live path). Two resource facts still bind the *ruling*, so they belong here:

| Concern | Constraint |
|---|---|
| Memory-path runtime fit (if hybrid ruled) | Parakeet + a whisper-turbo second pass must both complete **inside FR-11's 5-minute post-close window**, in the **Afterword subprocess** (D-12), within the **~3GB transient peak** the spec §5 RAM budget allows during that window. An accuracy win that cannot run in that envelope on this CPU is not a viable ruling — the bake-off must note runtime viability, not accuracy alone. |
| Bake-off run itself | Load models **sequentially**, never co-resident: `whisper-large-v3-turbo` (CT2 int8) and Parakeet TDT 0.6B are each large enough that holding two plus the harness risks paging on the 8GB machine. State `intra_op_num_threads` used. This is offline batch work with no latency budget — correctness and RAM safety over speed. |

**Flag (bold, per the rules): the live-path WER result feeds a *latency-adjacent* decision without being a latency number.** If Moonshine's live WER exceeds ~12%, the §9 gate says recalibrate every downstream **text-keyed** threshold — and several of those (the reflex selector's question/command/musing classifier, the fused endpointer's semantic-completeness signal, HP2) sit in the perceived-latency path. P-3 does not measure that latency; it measures the WER that those thresholds *assume*. The recalibration itself is M3a/M5 work.

## 7. Config keys

The bake-off is a hand-run measurement, so its knobs are **CLI arguments with defaults**, not `malang.toml` (FR-13 governs *runtime* config; a one-off script is not runtime). Documented defaults:

```
--corpus       corpus/p3/            # dir of reference WAVs + hand-corrected transcripts + proper-noun tags (see §9)
--models       all                   # all | moonshine-small | moonshine-medium | parakeet | whisper-turbo (repeatable)
--threads      3                     # ORT / CT2 intra-op thread count (state it in the ruling)
--normalizer   standard              # standard (lowercase, strip punctuation) — applied IDENTICALLY across models
--report-cased (flag)                # ALSO report a punctuation/casing-preserving score — do not silently erase Parakeet's native-punctuation advantage
--seed-vocab   docs/p3-vocab-seed.txt# where the extracted proper-noun/word-error seed list is written (FR-18 input)
--dry-run      (flag)                # offline; exercises WER math + gate branches + formatter on synthetic ref/hyp pairs, imports no ASR engine
```

**Downstream config the ruling *sets* (documented here, created later — not by this gate):** the M3a live-model choice (`speech.stt_live.model = "moonshine-small|medium"`), and the M7 memory-path shape (`speech.stt_final.hybrid_second_pass = false` with its **kill-switch** — the whisper pass is off unless the gate ruled hybrid, and can always be turned off to fall back to Parakeet-solo). No kill-switch belongs to the *probe* itself: hard rule 5 governs *probabilistic runtime components*; a measurement script is not one (same reasoning P-1/P-2 recorded). The switch that matters is the memory-path ruling in §13, keyed off the measured proper-noun gap.

## 9. Files to create

| Path | Purpose |
|---|---|
| `scripts/measure_p3_stt.py` | The bake-off harness (design §6 `speech/` will later host the real modules; this is the measurement). Loads the reference corpus, runs each requested model over the same WAVs, computes **WER and proper-noun-error-rate** overall, **per passage type** (monologue / read / code-switched), and **proper-noun-only**; prints the `/measure` ruling block; writes the seed vocab list of word/name errors. Pure core (WER + proper-noun-error math, normalizer, per-passage aggregation, gate-branch selection, `percentiles`, formatter, seed-vocab extraction) is **import-clean**; every ASR engine import is **lazy** (inside its adapter) so the pure core, `--dry-run`, and the unit tests need no model installed — the P-1/P-2 pattern. |
| `tests/test_measure_p3_stt.py` | Unit tests for the pure core only: WER on known ref/hyp pairs, proper-noun-error-rate on tagged pairs, per-passage aggregation, gate-branch selection (solo / hybrid / swap; Moonshine >12% flag), arg-parse defaults+overrides, `--dry-run` smoke, seed-vocab extraction. No engine, no audio. |
| `corpus/p3/README.md` + manifest | The corpus layout and provenance: which WAV is which register, the hand-corrected reference transcripts, the proper-noun tags, **the pinned model revisions from §11, and the SHA256 hashes of the un-pinnable Moonshine CDN weights** (§13 silent-drift guard). **Owner decision (2026-08-02): the filled references + manifest + seed vocab are git-ignored too**, not just the WAVs — they carry real family/friend names, kept local and off GitHub; only name-free code, schema, `prompts.md`, and `README.md` are tracked. |
| `docs/p3-vocab-seed.txt` | Output artifact: the proper-noun near-misses and word errors this speaker/mic actually produced — the **seed of the FR-18 vocab list** and the misaki lexicon overrides. Generated by the run; committed so P-4/P-6/FR-18 can consume it. |

## 10. Files to change

| Path | Change | Risk |
|---|---|---|
| `docs/m0-measurements.md` | Replace the `## P-3 …(pending)` stub with the ruling: WER + proper-noun-error-rate per model, per passage type, the memory-path ruling, the Moonshine live-WER health check, the chosen live size | none — doc |
| `Phase 1/malang-phase1-plan.md` | Tick the P-3 item of the M0 checklist (line "STT bake-off (code-switched passage)") once ruled | none — doc |
| `.gitignore` | Ignore the raw voice WAVs under `corpus/p3/` (keep transcripts + manifest tracked) | low — verify no WAV is already staged |

## 11. New dependencies

**CONFIRMED by `docs-researcher` against primary sources (PyPI JSON, repo `LICENSE` files, HF API), 2026-08-01.** The hoped-for single-library path did **not** fully hold: `onnx-asr` covers **Parakeet TDT and Whisper but NOT Moonshine**, so the bake-off resolves to **three ASR libraries + `jiwer`**. That is still the right shape — `onnx-asr` gets Parakeet without the NeMo stack (the fear was justified — see below), Moonshine takes its own package, and the whisper challenger uses `faster-whisper` (CTranslate2), which *is* the "int8/CT2" the spec names, rather than `onnx-asr`'s Whisper path. All four are CPU-only with confirmed win_amd64 / Python 3.12 support.

| Package | Version | Role | CPU-only? | Windows / 3.12? | License |
|---|---|---|---|---|---|
| `onnx-asr` | 0.12.0 | Loads **Parakeet TDT 0.6B v3** (ONNX) — avoids NeMo entirely. Covers Whisper too, but we don't use that path. **Does not support Moonshine.** | **yes** — pure-Python wheel, runs on the installed `onnxruntime`; `uv.lock` already pins **onnxruntime 1.28.0** (from P-2), which satisfies its strict range `>=1.18.1,!=1.24.1,!=1.25.*,!=1.26.0` | **yes** — `py3-none-any` wheel; classifiers list 3.12 | **MIT** (repo `LICENSE`; PyPI `license` field empty — the CLAUDE.md trap) |
| `moonshine-voice` | 0.1.0 | Live-path candidate, **Moonshine v2 small + medium** streaming. (Not `useful-moonshine-onnx` — that is the old v1 package.) | **yes** — but bundles a native `.dll` loaded via **ctypes** inside the wheel (not pure-Python). No separate install, but **smoke-import on the machine** first to rule out a DLL-load surprise. | **yes** — `moonshine_voice-0.1.0-py3-none-win_amd64.whl` present | **MIT** for code + **English** models (repo `python/LICENSE`). Non-English variants are **non-commercial** — we use the `-en` models only (live path is English), so MIT holds; do not pull a non-English variant. |
| `faster-whisper` (+ `ctranslate2`) | 1.2.1 (+ ct2 4.8.1) | Memory-path challenger, **whisper-large-v3-turbo**; CT2 quantizes to **int8 at load** (`compute_type="int8"`) — no pre-quantized repo needed | **yes** — `ctranslate2` ships **cp312 win_amd64** wheels (a stale search snippet claimed otherwise; the live PyPI file list disproves it) | **yes** | **MIT** (both) |
| `jiwer` | 4.0.0 | Standard WER/CER — keeps the metric off hand-rolled code | **yes** — deps `click` + `rapidfuzz`; `rapidfuzz` ships prebuilt win_amd64/cp312 wheels | **yes** (`requires-python >=3.8`) | **Apache-2.0** (repo `LICENSE`; PyPI field empty again) |

**Model weights — manual, one-time downloads, pins recorded in `corpus/p3/README.md`:**

| Config | Source | Revision to pin | Weights license |
|---|---|---|---|
| Moonshine v2 **small** | Moonshine AI CDN `download.moonshine.ai/model/small-streaming-en/quantized/*` (via `moonshine-voice`) | **No native version/tag mechanism — mutable URL.** SHA256 the files on first download and record them as the de-facto pin (§13 silent-drift row). | MIT (English) |
| Moonshine v2 **medium** | CDN `…/medium-streaming-en/quantized/*` | same hash-yourself caveat | MIT (English) |
| **Parakeet TDT 0.6B v3** | HF `istupakov/parakeet-tdt-0.6b-v3-onnx` (fp32 + int8 ONNX) | commit `8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce` | **CC-BY-4.0** — the one non-MIT/Apache license here; **attribution required**, record it in a `NOTICE`/README, not just "permissive." Commercial use permitted, not gated. |
| **whisper-large-v3-turbo** (CT2) | HF `deepdml/faster-whisper-large-v3-turbo-ct2` | commit `4df90f75321148c3a29a9e2351b7ddf8f5b115a8` | MIT |

No CC-BY-NC or gated weights among the four. **Nothing is installed against the system 3.14 interpreter** — the `uv` venv is confirmed on **3.12.13** with `onnxruntime 1.28.0` already present, so the ONNX path inherits a runtime P-2 already proved on this machine. **Two implementation-day smoke checks before trusting the harness** (both cheap, both guarding the ctypes/DLL and ONNX-load failure classes this project exists to catch): `import moonshine_voice`, and an `onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3")` round-trip. These deps are needed anyway by `speech/stt_live.py` (M3a) and `speech/stt_final.py` (M7), so P-3 introduces nothing the project wasn't already taking.

## 12. Rules for implementation

Hard rules that bite here: **the working-style rule** (measure, don't assume; record the ruling; a missing run is honest, a fabricated WER is a lie), **the record is sacred** (memory-path accuracy is a Phase-2-fidelity decision, not a convenience — weight it above the live path), and **C-2** (CPU-only). Then:

1. **The hand-corrected reference is ground truth — protect it.** WER is only as honest as the reference. Hand-correct every passage, tag every proper noun (names, places, the "Malang"/family-name tokens), and mark each code-switch span's language. The corpus is a **fixed, versioned constant** (like P-2's 10-sentence corpus): the *same* WAVs, byte-identical, feed every model and every re-run, so cross-model and re-run comparisons are valid.
2. **Same audio, same normalization, across every model — decided once, applied identically.** Resample each WAV to each engine's required rate (typically 16 kHz) with one shared step; never let a per-model audio difference confound the WER. Apply the `--normalizer standard` transform (lowercase, strip punctuation) **identically** to every hypothesis and the reference. State the normalizer in the ruling.
3. **Do not silently erase Parakeet's one advantage.** The memory path is the *durable record*, and Parakeet's **native punctuation + no silence-hallucination** is a record-quality edge that standard WER normalization throws away. Report the normalized WER **and** (`--report-cased`) a punctuation/casing-preserving note, so the ruling weighs readability of the permanent transcript, not just token error. §4 says errors in memory poison Phase 2 forever — punctuation and casing are part of that fidelity.
4. **Proper-noun-error-rate is the number that decides the hybrid — report it separately and per-passage.** A small *overall* WER gap can hide a large proper-noun gap on exactly the code-switched spans, and proper nouns are precisely what FR-18 and the misaki lexicon exist to fix. Compute error rate over the **tagged proper-noun tokens alone**, broken out by passage type, and make the ruling read **code-switched proper-noun error rate** as the primary deciding number — the P-2/HP16 parallel: never let a flattering aggregate bury the tail that will actually bite.
5. **Guard against empty/garbage transcripts — do not average them as "just a high WER."** If a model returns empty or obvious garbage on audio that demonstrably contains speech (the P-2 silent-synthesis failure class, mirrored), flag it as an engine failure in the ruling rather than folding a meaningless 100%+ WER into an average that looks like a legitimate loss. A model that *fails* is a different finding from a model that *transcribes poorly*.
6. **Two rulings, stated separately.** (a) **Memory path:** Parakeet-solo vs Parakeet+whisper-hybrid vs whisper-straight-swap, decided on the code-switched proper-noun gap **and** the §6 runtime-viability check (does the winner fit FR-11's window + Afterword RAM?). (b) **Live path:** is Moonshine's live WER **≤ ~12%** (if not, record the downstream recalibration flag loudly), and **small vs medium** — the accuracy gain of medium weighed against its live-CPU cost (the cost side is M3a's to confirm; P-3 supplies the accuracy delta).
7. **Emit the seed vocab list.** Every proper-noun near-miss and recurring word error the run finds is written to `docs/p3-vocab-seed.txt` — the FR-18 list's first content and the misaki lexicon's override candidates. "Word errors seed the FR-18 vocab list" is a §9 deliverable, not a nice-to-have.
8. **This is not a test.** It lives in `scripts/`, is run by hand, and loads real models on purpose. It must never be collected by pytest — the pure helpers are what the unit tests import (`tests/conftest.py` already puts `scripts/` on `sys.path` from P-2), and every engine import stays lazy so collection touches no ASR runtime. Define `percentiles` locally if needed (P-2 precedent; do not couple to unmerged P-1).

## 13. Failure modes

New or touched rows of spec §8 — each a case `chaos-engineer` may later name, and each a branch the ruling must be ready to take:

| Case | Behaviour |
|---|---|
| Parakeet within noise of whisper on the code-switched passage | **Parakeet ships solo** (§9). The whisper second pass is not built at M7; `alternates` stays unused. Record the gap and the noise floor. |
| Whisper dominates across the board | **Straight swap** — whisper-turbo becomes the memory-path model, provided it fits FR-11's 5-min window + Afterword RAM (§6). If it wins on accuracy but not on runtime fit, that tension is itself the finding — record it; Parakeet-solo may still win on viability. |
| Material gap on code-switched / proper-noun spans **only** | **Parakeet primary + whisper-turbo second pass** on low-confidence/language-flagged turns; both hypotheses stored in the `amend` event's `alternates`, in the Afterword subprocess, within FR-11's window (§9, §6.1). Built at M7; `speech.stt_final.hybrid_second_pass` ships with its kill-switch. |
| Moonshine live WER > ~12% | Downstream-wide flag: recalibrate **every text-keyed threshold** (reflex selector, fused endpointer semantic score, router escalate features — HP2). Record it prominently; it changes M3a/M5 calibration, not just the STT choice. |
| A model returns empty / garbage on real speech | Rule 5's guard: flag as an **engine failure**, not a high WER averaged into the score. A failing engine and a poor engine are different rulings. |
| Corpus lacks real code-switching or proper nouns | **Validity failure, not a pass.** A flattering distribution lets every model clear the bar and the gate rules on fiction. The corpus composition (three registers, real Urdu/Pashto↔English switches, "Malang"+family names) is a precondition of a valid P-3, checked before any number is trusted. |
| Hybrid wins accuracy but blows FR-11 window / Afterword RAM | Not a viable ruling as-is (§6). Record it; the fallback is Parakeet-solo, or whisper-turbo scoped to fewer flagged turns — a runtime decision, not an accuracy one. |
| Moonshine weights drift silently (mutable CDN URL, no version pin — §11) | The `moonshine-voice` weights come from a mutable `download.moonshine.ai` URL with no tag/hash mechanism; a future re-run could transcribe against changed weights with no signal — a silent-degrade class this project exists to catch. **SHA256 the files on first download, record the hashes in `corpus/p3/README.md`, and verify them before any re-run;** a hash mismatch aborts loudly rather than producing a quietly-different WER. |

## 14. Test plan

- **Unit (pure core only, no engine, no audio):** WER on known ref/hyp pairs (incl. insertions/deletions/substitutions); proper-noun-error-rate over tagged tokens; per-passage aggregation; gate-branch selection (solo / hybrid / swap, and the Moonshine >12% flag); arg-parse defaults + overrides; seed-vocab extraction from a known error set; `--dry-run` exits 0 and prints a ruling block without importing any ASR engine.
- **Contract:** none — the §6.3 `STT-final` / `STT-live` interface tests arrive with `speech/stt_final.py` (M7) and `speech/stt_live.py` (M3a). P-3 evaluates candidates, it does not implement the boundary.
- **Pipeline harness:** none — P-3 is offline batch over WAV fixtures, not the Pipecat graph.
- **Manual (the measurement itself):**
  1. Record ~4 min on the **real mic**: monologue + a read passage + a deliberately code-switched passage, including "Malang" and family names spoken naturally. Hand-correct into reference transcripts; tag proper nouns and code-switch spans.
  2. Confirm the `uv` venv is Python **3.12**; install the confirmed ASR deps (§11); download the four model weights per `corpus/p3/README.md`.
  3. `python scripts/measure_p3_stt.py --models all` → per-model WER + proper-noun-error-rate, broken out per passage type and proper-noun-only, plus the seed vocab list.
  4. Paste the ruling into `docs/m0-measurements.md`: the memory-path ruling (with runtime-viability note), the Moonshine live-WER health check + chosen size, and the `docs/p3-vocab-seed.txt` pointer.

No test writes under `memory/raw/`. No test calls the Claude API. No test imports an ASR engine.

## 15. Definition of done

- [ ] Milestone exit test (design §7 M0): **P-3 gate ruled and recorded** — quote per-model **WER and proper-noun-error-rate**, broken out **per passage type** (monologue / read / code-switched) and **proper-noun-only**, the **memory-path ruling** (Parakeet-solo / hybrid / whisper-swap) with its runtime-viability note, the **Moonshine live-WER health check** (≤ ~12%?) and chosen **small vs medium**, plus the thread count and normalizer used
- [ ] `python .claude/hooks/invariant_lint.py --full` clean
- [ ] `pytest -q` green (WER + proper-noun + gate-branch + arg-parse + seed-vocab unit tests; no engine, no network)
- [ ] No session written by this code (it writes none) — schema check trivially holds; confirmed no `memory/raw/` write
- [ ] `spec-guardian` run; BLOCKING findings resolved
- [ ] `security-review` — model download over network is one-time (like P-2); otherwise local, no credentials, no egress at run time; confirm the corpus-WAV `.gitignore` split leaks no personal audio into the repo
- [ ] `docs/p3-vocab-seed.txt` written — the FR-18 / misaki-lexicon seed list
- [ ] P-3 ruling written into `docs/m0-measurements.md` (replacing the pending stub)
- [ ] Probe defaults documented in `--help`; no setting in any tracked runtime file
- [ ] **Usable that evening** — trivially met; the bake-off leaves the runtime untouched
- [ ] Build-plan P-3 checkbox ticked; M0 note written
- [ ] (Not required) `latency-auditor` — P-3 grades accuracy, not latency; the only latency-adjacent link (Moonshine WER → downstream text-keyed thresholds) is flagged in §6, recalibrated at M3a/M5

## 16. Out of scope

- **Live-path latency (M3a).** P-3 grades Moonshine's *accuracy*, not its ~107ms live latency; the streaming round-trip is measured with the real Pipecat graph at M3a. This is the most likely misread of P-3 — it is the accuracy sibling of the P-2/HP16 "RTF is not first-audio" flag.
- **Building the FR-18 post-corrector and the misaki lexicon (FR-18, P-4/P-6, M7).** P-3 *seeds* the vocab list; the double-metaphone + fuzzy-match rewriter and the phoneme overrides are built later. P-3 produces `docs/p3-vocab-seed.txt` and nothing more.
- **Building the hybrid second-pass runtime (M7).** P-3 *decides whether it is needed*; the Afterword `amend`/`alternates` wiring and `hybrid_second_pass` config are M7 work.
- **Endpoint and reflex tuning (M3a/M5, HP2/D-9/D-15).** P-3 supplies the live WER those thresholds assume; the recalibration (if WER > ~12%) happens where those components are built.
- **Sustained full-stack duplex load (P-5).** P-3 runs the ASR models offline and one at a time; whether they hold up co-resident under AEC + Silero + smart-turn + Kokoro + fsyncing Scribe is P-5.
- **Voice/name *pronunciation* (P-4/P-6).** P-3 measures whether names are *recognized* (STT); whether "Malang" and family names are *spoken* correctly (TTS/misaki) is P-4/P-6. The two share the vocab list; they are opposite ends of it.
- Anything that reads from `memory/`.
