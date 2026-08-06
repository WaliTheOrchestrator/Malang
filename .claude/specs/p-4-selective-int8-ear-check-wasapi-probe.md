# P-4 — Selective-int8 ear check + WASAPI probe

**Milestone:** M0 · **Branch:** `feat/p-4-selective-int8-ear-check-wasapi-probe` · **Created:** 2026-08-03
**Spec version:** 1.1 · **Status:** done (shipped 2026-08-06 via PR #5, squash-merged `c78f41a`; P-4a → ship fp32 — negative control failed twice, difference below blind-ABX threshold, selective-int8 kept for a P-5 revisit; P-4b → 40.0ms mains+battery ≤50ms confirmed; rulings in `docs/m0-measurements.md`. Owner-approved 2026-08-03; pre-approval research resolved by docs-researcher; spec-guardian BLOCKING B-1 fixed)
**Governing docs:** malang-phase1-spec.md §9 (P-4), §5 (TTS-first-audio + audio-output budget, exclusive-mode rejection), §8 (TTS underrun) · design §2 (TTS stack "selective-int8 ONNX per spec P-4"; Audio I/O "WASAPI shared-mode event-driven"), §7 (M0 exit, risks), D-4 (`render_reflexes.py`), D-10 (micro-first-chunk, "P-4 ear check gates") · hard-problems HP13 (int8 voice drift — the ear test IS the gate), HP14 (WASAPI buffer minefield — log the negotiated size), HP16 ("blind quantize_dynamic = audible static → selective int8") · CLAUDE.md hard rule 4 (one voice; every speed gain passes an ear test)

---

## 1. Overview

P-4 is the fourth measurement gate, and the only M0 gate that a stopwatch cannot decide — it is judged **by ear**. It settles two independent questions that both sit on Malang's voice. **(a) The int8 ear check:** can a listener, blind, tell the **selectively-quantized int8** Kokoro build apart from the **fp32** build across ten emotionally-varied sentences — *including Malang saying his own name and family names*? int8 is a **RAM and thermal-headroom** lever, not a speed rescue — **P-2 already PASSED on fp32** (aggregate p50 RTF 0.529 mains / 0.555 battery, well under the 0.8 gate; `docs/m0-measurements.md`), so speed is not the binding constraint the way it looked when the budget was drafted. int8's honest value on this 8GB/2GB-reserved machine is the **~310MB→~90MB memory delta** (verified against the actual files) and the thermal margin it buys **P-5**'s sustained-duplex load — while §5 line 127 still names the shipping TTS build "selective-int8 Kokoro." HP13 warns quantization flattens timbre worst on emotional range, "exactly where presence lives," and no metric catches "he sounds slightly less alive" — so ears, not benchmarks, are the gate. **(b) The WASAPI probe:** what output-buffer latency does a **shared-mode, event-driven** WASAPI stream actually negotiate on this laptop's built-in speakers? The §5 budget claims 30–40ms p50 / 50ms p95 and HP14 warns the driver may silently hand back a fat buffer — so we measure the negotiated size rather than assume it. The two halves share nothing methodologically (one is subjective and human-graded, one is an objective device measurement); they are bundled because both are cheap M0 preconditions on the same subsystem. Like P-2 and P-3, P-4 needs no API key and no network — it is fully local. It is hand-run: two probe scripts plus a one-time build utility, not runtime modules and not pytest tests. Without P-4 ruling, every §5 line that assumes int8 speed and a 50ms output path is an assumption, and D-10's clause-joint TTS start has no ear-test floor to stand on.

## 2. Governing requirements

Quoted, not paraphrased. Every line is something the reviewer will check the ruling against.

| Source | Requirement (quoted) |
|---|---|
| §9 P-4 | "Selective-int8 Kokoro listening check (10 sentences, int8 vs fp32, blind A/B by ear — including \"Malang\" and family names via the misaki lexicon) + shared-mode event-driven WASAPI buffer measurement" |
| §9 P-4 gate | "int8 judged indistinguishable → int8 ships (blind quantize_dynamic is expected to FAIL — use a selectively-quantized build). Lexicon names pronounced correctly → bake into `render_reflexes.py`. Output ≤50ms → confirmed. Failing → fp32 and revise honestly." |
| §9 P-4 (battery clause) | "v1.2: repeat P-2 and the M3 round-trip ON BATTERY — a budget validated only on mains is fiction for a laptop; log AC/DC per session thereafter." — **the P-2-on-battery half of this clause is already DISCHARGED** by the P-2 ruling (mains AND battery, 2026-07-30, `docs/m0-measurements.md`); the M3 round-trip battery run is M3b's (design §7 / `malang-phase1-plan.md`), not P-4's. |
| §5 (latency) | "TTS first audio of first micro-chunk (selective-int8 Kokoro, ≤7 words) \| 300ms \| 450ms" — the int8 build P-4a passes is the one this budget names. |
| §5 (latency) | "Audio output path (WASAPI **shared-mode** event-driven, 20ms frames) \| 30–40ms \| 50ms" — the number P-4b measures. |
| §5 (re-baseline) | "Exclusive-mode WASAPI is rejected as default: it locks the render device against every other app (standing FR-14 violation), rejects the 16kHz-mono contract, and buys ~15–25ms against a 500–1,100ms network term." — P-4b probes **shared** mode; it does not adopt exclusive to hit 50ms. |
| §8 (edge) | "TTS underrun (CPU spike, synthesis slower than playback) \| Buffer one sentence ahead; on underrun, pause at sentence boundary (natural), never mid-word; log `tts_underrun`…" — the negotiated buffer P-4b finds feeds this. |
| HP13 | "int8 quantization can subtly flatten timbre (worst on emotional range, exactly where presence lives)… no metric catches 'he sounds slightly less alive'. **P-4's blind A/B listening check is the gate — ears, not benchmarks, and re-run it after any model or runtime update.**" |
| HP14 | "some drivers misreport buffer capabilities… **Probe device capabilities at startup and log the negotiated buffer size** — if the driver hands back a fat buffer, the daily one-liner should say so… Budget assumes ≤50ms p95; if a device can't deliver it, record the honest number and move on — 30ms of output buffer is not worth a fragile audio stack." |
| HP16 | "selective int8 (**blind quantize_dynamic = audible static**), and the misaki lexicon so the presence can say its own name." — the build under test is *selectively* quantized; the off-the-shelf blind build is a negative control, not the candidate. |
| D-4 | "Reflex clip set is a build artifact: `scripts/render_reflexes.py` regenerates all clips from a phrase list whenever the voice config changes." — the gate that says "bake into `render_reflexes.py`" feeds this; P-4 confirms names are sayable, it does not build the reflex set. |
| D-10 | "prosody-safe joins… **P-4 ear check gates**; fallback to sentence-level costs +100ms, taken honestly." |
| CLAUDE.md rule 4 | "**One voice everywhere** — the P-6 Kokoro voice… Malang pronounces his own name correctly. **Every speed gain passes an ear test.**" |
| C-2 | "CPU-only local inference (no dGPU available)." |
| C-9 | one-voice-everywhere is a hard constraint — int8 must not become a second, subtly-different timbre. |
| CLAUDE.md working style | "Say what you actually measured, not what should happen." / "Every speed gain passes an ear test." — record the ruling; a fp32-only outcome is an honest branch, not a failure. |

## 3. Depends on

- **Specs / milestones:** none upstream in the pipeline. P-4 is independent of P-1 (no cloud, no key) and can be run to a recorded ruling now — like P-2/P-3 it is fully local and free. Ruling P-4 does **not** close M0 on its own: the design §7 exit test needs P-1/P-2/P-3/P-4 (and P-5/P-6 are pending too). P-4 gates the **TTS build** for M3a (does the reflex/thought path synthesize with int8 or fp32?), confirms the **name-pronunciation override** that D-4's `render_reflexes.py` and every reflex clip depend on, and produces the measured **output-buffer number** that M3a's shared-mode WASAPI stage is graded against.
- **P-2 (RULED, PASSED):** P-4a re-uses P-2's proven install path — `kokoro-onnx` on the 3.12 venv with `onnxruntime` already present, and `Kokoro.from_session(...)` to load an arbitrary `.onnx` build (the same path swap P-2's `--build` used). P-2 also already discharged the **battery** half of the §9 P-4 battery clause. The int8-vs-fp32 *speed* delta is P-2's `--build quantized` rung, not P-4's concern — **P-4a grades quality only** (§16).
- **P-3 (RULED):** the family names spoken in the ear-check corpus come from `docs/p3-vocab-seed.txt` (present locally; git-ignored — real names). P-3 is the *recognition* end of that shared list; P-4 is the *pronunciation* end (§16).
- **Measurement gates:** this **is** a gate (two sub-gates, P-4a and P-4b — both must rule for the P-4 checkbox). None precedes it hard. **P-6 (voice identity) is pending and is NOT a hard prerequisite** — int8 quantizes the *shared* Kokoro model, and the 26 voices are separate style embeddings in `voices-v1.0.bin`, so the int8-vs-fp32 distinguishability ruling is **voice-independent**. P-4a runs on the config-default voice now; hard rule 4 ("re-run the ear test after any model change") then requires a confirmation pass on the **P-6 winner** once it lands. State this dependency in the ruling.
- **Hardware / environment:** the reference **i3-1315U**; for P-4b, the laptop's **built-in speakers** (the device the §5 budget is written for — a Bluetooth or USB DAC negotiates a different buffer and is a different measurement). Mains for the headline numbers; a battery **spot-check** of the negotiated buffer is cheap and worth recording (power-throttling can change driver behaviour). P-4a needs a **quiet room and the real playback path**, and — for grading honesty — ideally a **second listener** (see §12).
- **A prerequisite artifact, not a download:** the **selective-int8 build** must exist before P-4a can rule. It is *produced*, not fetched (the release ships only the blind `kokoro-v1.0.int8.onnx` — confirmed blind, §11 item 1). The quantization recipe is **resolved**: exclude the ISTFTNet vocoder post-conv (`^/decoder/generator/conv_post/Conv`), see §11 item 1.

## 4. Contracts

**No new contract.** P-4 defines no §6.3 module boundary. `speech/tts.py` will formalize the `TTS` contract at M3a and the audio-output stage will formalize its device handling then; P-4a times/plays raw synthesis and P-4b opens a raw `sounddevice` stream — both call the engines' own APIs directly, as measurements, not as the modules. What P-4 *produces* for those future modules is a **decision** (which build ships, is the 50ms budget real) and, if P-4a passes, a **build artifact** (the confirmed selective-int8 `.onnx`) plus a confirmed **name-override method**.

## 5. Log schema impact

**None.** Both probes write only to `docs/m0-measurements.md`, a recipe/hash note under `docs/`, and optional CSVs in the scratch tree. They write nothing under `memory/raw/` and touch no session log. Worth stating because the ruling *configures downstream behaviour* (which build M3a loads, whether exclusive mode is ever allowed) — but that is config (§7), not schema. No `schema-change` skill is invoked.

## 6. Latency and resource budget

P-4 straddles two §5 rows, one per sub-gate:

| §5 stage | Budget p50 | Ceiling p95 | Which sub-gate |
|---|---|---|---|
| Audio output path (WASAPI shared-mode event-driven, 20ms frames) | 30–40ms | 50ms | **P-4b measures this directly** — the negotiated buffer/stream latency PortAudio reports. |
| TTS first audio of first micro-chunk (selective-int8 Kokoro, ≤7 words) | 300ms | 450ms | **P-4a gates the *build* this row names**, but does **not** measure this number. |

**Flag (bold, per the rules): P-4a is a *quality* gate, not a latency one.** It decides whether the int8 speed/RAM lever may be pulled by proving the pulled lever is *inaudible* — but it measures indistinguishability by ear, not milliseconds. The first-micro-chunk 300ms latency is M3a's with the real micro-chunk pipeline (HP16/D-10), exactly as P-2's RTF was "not the 300ms number." **Second flag: P-4b's number is the API/driver buffer, not the acoustic path.** PortAudio's reported stream latency is the shared-mode output buffer, not the phone-recorded speaker-to-ear gap (HP10); the ≤50ms gate is the *output-buffer* budget, and the end-to-end perceived number is instrumented at M3a/M3b. **Third flag (docs-researcher):** PortAudio documents a shared-mode WASAPI latency **floor of ~20ms**, so the 30–40ms/50ms budget sits only ~10–20ms above the floor — real but modest headroom, worth stating in the ruling rather than implying comfort. Resource footprint is trivial: P-4a loads one ORT session at a time (fp32 ~310MB / int8 ~90MB — never co-resident); P-4b opens one output stream. Both sit well inside the 2GB reservation. State the ORT thread count used (design §2 start value 2–3 for Kokoro).

## 7. Config keys

Both probes are hand-run measurements, so their knobs are **CLI arguments with defaults**, not `malang.toml` (FR-13 governs *runtime* config; a one-off script is not runtime). Documented defaults:

```
# scripts/build_kokoro_selective_int8.py — produce the candidate build (one-time)
--fp32          models/kokoro-v1.0.onnx        # source fp32 model
--out           models/kokoro-v1.0.int8-selective.onnx
--exclude       '^/decoder/generator/conv_post/Conv'  # vocoder post-conv kept fp32 (§11 item 1); confirmed present via onnx.load first
--report        docs/p4-int8-build.md          # records the exclusion set + SHA256 of the produced build

# scripts/measure_p4_int8_ear.py — the blind ABX ear check
--builds        fp32,selective,blind           # 'blind' = models/kokoro-v1.0.int8.onnx, the NEGATIVE CONTROL
--voice         af_heart                        # §6.4 default; P-6 owns identity — re-run on the P-6 winner (rule 4)
--trials        24                              # ABX trials per contrast; gate reads binomial significance, not a vibe
--seed          <int>                           # fixes trial order + which build is X; reproducible, still hidden from grader
--grader        <label>                         # who is judging; a 2nd grader is a separate --grader run
--threads       3                               # ORT intra_op_num_threads (state it in the ruling)
--dry-run       (flag)                          # offline; exercises ABX stats + gate branches + formatter on synthetic responses; imports no engine

# scripts/measure_p4_wasapi.py — the shared-mode event-driven output-buffer probe
--device        default                         # built-in speakers; a non-built-in device is a different measurement
--frame-ms      20                              # §5 frame size
--samplerate    24000                           # Kokoro's native rate (resample contract is M3a's; state what was used)
--label         mains|battery                   # power label recorded with the number
--dry-run       (flag)                          # offline; exercises the ms-from-frames math + ≤50ms gate branch; opens no device
```

No kill-switch belongs to a *probe* — hard rule 5 governs *probabilistic runtime components*; a measurement script is not one (the reasoning P-1/P-2/P-3 recorded). The switches the ruling *sets* live downstream and are created later, not by this gate:

- `speech.tts.model_build = "selective-int8" | "fp32"` — the ship decision. Its **kill-switch is the fp32 value**: any doubt about int8 drift after a model/runtime change flips back to fp32 and pays the honest cost (HP13). Default is whatever P-4a ruled.
- `audio.output.exclusive = false` — shared mode is the standing default (§5, HP14); exclusive is **strictly opt-in** and never adopted merely to reach 50ms (it is an FR-14 violation). P-4b confirms the shared-mode number the default is written against.

## 9. Files to create

| Path | Purpose |
|---|---|
| `scripts/build_kokoro_selective_int8.py` | One-time build utility: `quantize_dynamic` on `kokoro-v1.0.onnx` with `nodes_to_exclude` pinned to the **ISTFTNet vocoder post-conv** (`^/decoder/generator/conv_post/Conv` — §11 item 1), the node HP16's "no metric catches it" was proven on. **First `onnx.load()` the actual model and confirm a `conv_post` node exists** before excluding (§11 caveat — node names are export-specific). Records the exclusion set, the source-fp32 hash, and the produced build's SHA256 to `docs/p4-int8-build.md`. Pure core (exclusion-list assembly + hashing + report) import-clean; the `onnx` / `onnxruntime.quantization` imports are lazy. |
| `scripts/measure_p4_int8_ear.py` | The **blind ABX** probe. Renders the fixed 10-sentence corpus — a **tracked template with name placeholders**, real names injected at run time from a git-ignored local file (§12 rule 3, B-1) — in each `--build`, presents randomized ABX trials (grader hears X then A/B, decides X==A or X==B), records responses, computes the **binomial significance** of the correct-rate vs 50%, and tallies **name-pronunciation correctness** ("Malang" + family names) separately. Prints the `/measure` ruling block. Pure core (ABX stats, seeded trial/label assignment, name-tally, gate-branch selection, formatter, `percentiles` if needed) import-clean; the `kokoro_onnx` import is lazy — pure core, `--dry-run`, and the unit tests need nothing installed (the P-2/P-3 pattern). |
| `scripts/measure_p4_wasapi.py` | The **shared-mode event-driven WASAPI** output-buffer probe. Opens a `sounddevice` output stream with `WasapiSettings(exclusive=False)` (event-driven is PortAudio's WASAPI default), reads the **negotiated** stream latency + buffer, converts to ms, prints the ruling against the ≤50ms gate. Pure core (ms conversion, gate branch, formatter) import-clean; the `sounddevice` import is lazy. |
| `tests/test_measure_p4_int8_ear.py` | Unit tests for the ear-probe pure core only: ABX binomial significance on known correct/total counts, seeded trial+label assignment is deterministic, name-correctness tally, gate-branch selection (indistinguishable / distinguishable / negative-control-failed), arg-parse, `--dry-run` smoke. No engine, no audio. |
| `tests/test_measure_p4_wasapi.py` | Unit tests for the WASAPI-probe pure core only: ms-from-frames/samplerate conversion, ≤50ms gate branch (pass / over-budget), arg-parse, `--dry-run` smoke. No device. |
| `docs/p4-int8-build.md` | The selective-int8 build's provenance: the exclusion recipe used, the SHA256 of the produced `.onnx`, and the source fp32 hash — so a future re-run can prove it graded the *same* build (the P-3 silent-drift guard, mirrored for a produced artifact). |

## 10. Files to change

| Path | Change | Risk |
|---|---|---|
| `docs/m0-measurements.md` | Replace the `## P-4 …(pending)` stub with the two rulings: (a) int8 ABX result + name-correctness + which build ships; (b) the negotiated shared-mode WASAPI buffer/latency in ms vs the 50ms gate, with power label | none — doc |
| `Phase 1/malang-phase1-plan.md` | Tick the P-4 item of the M0 checklist once **both** sub-gates rule | none — doc |
| `pyproject.toml` | (1) Add a `p4` (or `probe`) optional extra exposing `sounddevice` for the P-4b probe — **do not** promote it to base: the `recorder` extra deliberately keeps PortAudio out of every install, and the P-4b unit tests are pure-core with a lazy import. (2) Add **`onnx` (~1.22.0, Apache-2.0)** to a `build`/`dev` extra — `onnxruntime.quantization` is **NOT** bundled and errors without it (§11), and it is build-time-only (not runtime). | low — dependency wiring only; both confirmed installable on the 3.12 venv |

(`docs/p4-int8-build.md` is **created**, see §9.)

## 11. New dependencies

**CONFIRMED by `docs-researcher` against the actual `.venv` (Python 3.12.13, Windows 11, i3-1315U) and primary sources, 2026-08-03** — installed versions exercised, not inferred: `kokoro-onnx` 0.5.0, `onnxruntime` 1.28.0, `sounddevice` 0.5.5, `phonemizer` 3.3.2, `espeakng-loader` 0.2.4 (bundled espeak-ng 1.52.0).

| Package | Version | Why | CPU-only? | Windows/3.12? | License |
|---|---|---|---|---|---|
| `sounddevice` | `0.5.5` (already in `uv.lock` via the `recorder` extra) | Opens the shared-mode event-driven WASAPI output stream and reads the **negotiated** latency via `WasapiSettings(exclusive=False)` + `Stream.latency`. Event-driven is PortAudio's default **and only reachable** shared mode (`paWinWasapiPolling` exists natively but sounddevice never wires it up). | **yes** — pure audio I/O | **yes** — PortAudio bundles WASAPI on `win_amd64`; the intended production audio lib (design §2). Expose via a `p4`/`probe` extra, **not** base (§10). | **MIT** |
| `onnx` | `1.22.0` | **NET-NEW, build-time only.** `onnxruntime.quantization` is **NOT bundled** with the CPU `onnxruntime` wheel — `import onnxruntime.quantization` → `ModuleNotFoundError: No module named 'onnx'` on this exact venv, and `onnx` is not pulled transitively by `onnxruntime` or `kokoro-onnx`. `build_kokoro_selective_int8.py` needs it (`quantize_dynamic` **and** `onnx.load()` to read graph node names). | **yes** — no GPU pull | **yes** — `cp312-abi3-win_amd64` wheel on PyPI | **Apache-2.0** (repo `LICENSE`; PyPI classifier empty — the P-2 blank-metadata trap again) |

`onnxruntime` (already present from P-2) provides `quantize_dynamic(model_input, model_output, op_types_to_quantize=None, nodes_to_exclude=None, weight_type=QuantType.QInt8, …)` — signature read from the installed 1.28.0 source. `nodes_to_exclude` takes **node names**, not op types, so the build script must `onnx.load()` the model and read `graph.node` to get them. Scope `onnx` to a `build`/`dev` extra: build-time tool, not needed by runtime `speech/tts.py`.

**The two pre-approval questions are now RESOLVED (docs-researcher, 2026-08-03):**

1. **Selective-quantization recipe — RESOLVED, with one verify-before-hardcode caveat.**
   - The shipped `kokoro-v1.0.int8.onnx` is a **blind/default ORT dynamic-quant build** (traced to `taylorchu/kokoro-onnx` v0.2.0's `kokoro-quant-convinteger.onnx`, byte-size match; the `convinteger` name is an ORT default-op artifact, not a curated recipe; no documented exclusion set or listening test). Confidence: *likely* (strong circumstantial, not an author statement). **So the spec's roles hold — it is the negative control; no swap.**
   - Known-good exclusion set (only public documented methodology, `adrianlyjak/kokoro-onnx-export`): **exclude the ISTFTNet vocoder's final post-conv, node-name pattern `^/decoder/generator/conv_post/Conv`** for dynamic quantization (add `/decoder/generator/resblocks` if trialing static). That source flagged this node **by ear after an automated mel-distance metric missed it** — a live instance of HP16 ("no metric catches it"). **LayerNorm/InstanceNorm need no explicit exclusion** — ORT's quantizers don't target those op types by default.
   - **Caveat for `docs/p4-int8-build.md`:** that node name was verified against a *different* ONNX export than `kokoro-v1.0.onnx`. `build_kokoro_selective_int8.py` MUST `onnx.load()` the actual model and confirm a `conv_post` node exists before hard-coding the exclusion regex — a five-line check, not an assumption.
2. **Name-override method — RESOLVED; the design's "misaki lexicon" is confirmed wrong for this runtime.**
   - The real, locally-tested mechanism is `Kokoro.create(text, voice, is_phonemes=True)` fed a **pre-phonemization override table**: phonemize the sentence normally (`phonemizer` → IPA-with-stress over Kokoro's 114-symbol vocab), string-substitute the name's auto-phonemized IPA span with a hand-tuned correction, then synthesize with `is_phonemes=True`. `is_phonemes`, `_split_phonemes`, and `from_session` all exist in 0.5.0 as assumed.
   - The espeak-ng `[[phoneme]]` inline escape and any dictionary/`add_dictionary` override are **NOT reachable** through this stack (`phonemizer` calls the low-level `espeak_TextToPhonemes` C API, which has no user dictionary and treats `[[…]]` as literal text) — tested and confirmed locally. Default "Malang" → `mˈælæŋ`, not obviously the intended Pashtun pronunciation, so the override is real work, not a formality.
   - **Action (design-doc fix, tracked separately — §16):** flag to design §2 and the persona that "misaki lexicon" must read "phoneme-substitution table + `is_phonemes=True`" for the onnx runtime. Do not silently substitute.
3. **WASAPI negotiated-buffer read — RESOLVED.** `WasapiSettings(exclusive=False, …)`; read back `Stream.latency` (populated from `Pa_GetStreamInfo()->outputLatency` — the negotiated, not requested, value) × 1000 = ms for the ≤50ms gate; log `query_devices()[…]['default_low/high_output_latency']` as context only. `PaWasapi_GetFramesPerHostBuffer()` (a literal frame count) is **not bound** in sounddevice — `Stream.latency` is the only negotiated number reachable, which suffices for the gate. **Numeric context for the ruling:** PortAudio documents a shared-mode WASAPI latency **floor of ~20ms**, so the §5 30–40ms/50ms budget has real but modest headroom (§6).
4. **espeak-ng silent-audio class — RESOLVED, guard confirmed in-scope.** `hexgrad/kokoro#301` (open, 2026-03-05): a Windows UTF-8 phonemizer bug returns silent audio (no exception); reported on Spanish, but the root cause is non-ASCII byte handling, not the language. English phoneme output here is *also* non-ASCII (`ˈ æ ŋ`), and the hand-authored override table is the highest-risk non-ASCII surface — so §12 rule 5's per-render non-silence guard is correctly scoped and must **also cover `is_phonemes=True` override renders**, not only plain-text ABX renders.

These deps/mechanisms are needed anyway by `speech/tts.py` (M3a) and the audio-output stage (except `onnx`, which is build-time-only), so P-4 introduces essentially nothing the project was not already taking.

## 12. Rules for implementation

Hard rules that bite here: **rule 4** (one voice; Malang says his own name; **every speed gain passes an ear test**), **rule 5's spirit** (the int8 lever gets a config kill-switch to fp32, even though it is deterministic — because HP13 says drift is subjective and re-checkable on every model change), the **working-style rule** (record what the ears actually said; a fp32-only ruling is an honest branch, not a failure), and **C-2** (CPU-only). Then:

1. **The candidate is the *selective* build; the blind build is the negative control — and the control is a validity gate, not decoration.** Grade three renders: **fp32** (reference), **selective-int8** (candidate), and a **genuinely-blind int8** control — the off-the-shelf `kokoro-v1.0.int8.onnx` **if §11 item 1 confirms it is a blind dynamic quantization**, otherwise a purpose-built `quantize_dynamic` blind build. (If research finds the shipped release is *itself* selective, the roles swap: it becomes the candidate and the blind control is the one produced — the negative-control discipline is unchanged either way.) If the grader **cannot** reliably distinguish the *blind* build from fp32, the ear test is **not sensitive enough** (room, gear, grader, or corpus) and **no "indistinguishable" verdict on the selective build is trustworthy** — fix the test before ruling. This is the P-3 parallel: a corpus/method that lets everything "pass" rules on fiction. HP16 predicts the blind build *should* be audibly worse; if it isn't detectable, the instrument is broken.
2. **Blind means blind — and one person grading his own companion is not blind (the A-15 honesty rule, applied to ears).** Use **ABX**: the grader hears X (secretly fp32 or int8, chosen by `--seed`), then A and B, and must pick which of A/B equals X. Labels are hidden; the seed fixes the assignment reproducibly but the grader never sees it. Require a real trial count (`--trials 24` default) and read the **binomial significance** of the correct rate against 50% — "indistinguishable" means *not significantly above chance*, not "sounded fine once." Prefer a **second grader** who did not build the model; record each grader's result separately. Never let the person who chose the exclusion recipe grade only his own build unblinded.
3. **Grade emotional range, not just clarity — that is where int8 dies (HP13).** The fixed 10-sentence corpus MUST span calm, warm, emphatic, a question, and at least one heavy/tender line — because quantization flattens *emotional* timbre first, and a corpus of flat declaratives would let int8 pass on the easy distribution. Include the mandated content: **"Malang"**, **family names**, and **one code-switched line**. **The names never live in the tracked script (B-1 — the P-3 owner decision keeps real family/friend names off GitHub, `docs/m0-measurements.md`).** What is tracked is the corpus **template with name placeholders**; the real name tokens are injected at run time from a **git-ignored** local file (`docs/p3-vocab-seed.txt` or a git-ignored `corpus/p4/names.txt`). The ABX validity still needs a byte-stable corpus across builds and graders (like P-2's 10 sentences — cross-build comparison is only valid on identical text), so **pin the SHA256 of that local names file in `docs/p4-int8-build.md`** and verify it before each run — the same silent-drift guard the produced build gets. Template tracked, names local, corpus reproducible.
4. **Name correctness is a *separate* ruling from int8 distinguishability — report it on its own.** A build can be perfectly indistinguishable from fp32 and *both* can mispronounce "Malang." Tally name-pronunciation correctness independently, on both builds, using the §11 override method. "Lexicon names pronounced correctly → bake into `render_reflexes.py`" (§9) is a **precondition on baking reflex clips (D-4)**, not a byproduct of the int8 verdict. If names are wrong, that is a finding against the override method, recorded separately; do not bake until it is fixed.
5. **Guard against silent/degenerate audio on every render — the P-2 failure class, mirrored, now with two confirmed triggers.** (a) The espeak-ng path returns empty/silent audio with no exception on a Windows UTF-8 phonemizer bug (`hexgrad/kokoro#301`, still open; non-ASCII byte handling, and English phonemes here are non-ASCII too). (b) The Kokoro tokenizer **silently drops** any character not in its 114-symbol vocab — a hand-authored override string that uses an ASCII apostrophe `'` instead of the IPA stress mark `ˈ` loses a token with no error and can synthesize degenerate audio (confirmed locally). An ABX trial over a silent/degenerate A or B is meaningless (a silent pair is trivially "indistinguishable" — a false pass). So: check peak amplitude on **every** rendered clip — **including every `is_phonemes=True` override render**, not just plain-text ABX renders — before it enters a trial, and validate that each override phoneme string tokenizes to its expected length; on the first silent/empty/truncated clip, abort loudly and record nothing.
6. **P-4b measures the *negotiated* buffer, not the requested one (HP14).** Open the shared-mode event-driven stream, then read back what PortAudio/WASAPI actually negotiated (`Stream.latency`, and query the device's default/min period), and report **that** — a driver may silently inflate the buffer. State the device name, the frame size, and the sample rate used. Report the number honestly against ≤50ms; **if the built-in device cannot deliver ≤50ms in shared mode, record the real number and stop** — HP14: 30ms of output buffer is not worth a fragile audio stack, and exclusive mode is not adopted to force the gate green (§5, FR-14). Take a cheap **battery** spot-check too — power-throttling can move the negotiated period.
7. **These are not tests.** They live in `scripts/`, are run by hand, and load a real model / open a real device on purpose. They must never be collected by pytest — the pure helpers are what the unit tests import (`tests/conftest.py` already puts `scripts/` on `sys.path` from P-2), and every engine/device import stays lazy so collection touches no ONNX runtime and no PortAudio. Define `percentiles` locally if needed (do not couple to unmerged P-1).
8. **Record the voice-independence caveat and the re-run obligation.** State in the ruling that P-4a graded the config-default voice, that the int8 verdict is voice-independent (shared model, separate voice embeddings), and that rule 4 requires a **confirmation ABX pass on the P-6 winner** once P-6 rules — and after any Kokoro model or runtime update thereafter.

## 13. Failure modes

New or touched rows of spec §8 — each a case `chaos-engineer` may later name, and each a branch the ruling must be ready to take.

| Case | Behaviour |
|---|---|
| Selective int8 **distinguishable** from fp32 (grader significantly above chance) | int8 fails the ear test. Try **one** alternative exclusion recipe (a broader fp32 set); if still audible, **ship fp32** and pay the speed/RAM cost honestly in the ruling (§9 "Failing → fp32 and revise honestly"). Record which §5 line loosens. The D-10 clause-joint fallback (+100ms sentence-level) is a *different* lever (HP13) and is M3a's, not P-4's. |
| **Negative control fails** — grader can't distinguish even the *genuinely-blind* int8 control (§12 rule 1) from fp32 | The ear test is not sensitive (room/gear/grader/corpus). **No "indistinguishable" verdict is trustworthy.** Do not rule P-4a until the instrument detects the build HP16 says is audibly worse — fix the setup, add a grader, or harden the corpus first. |
| Names ("Malang" / family names) mispronounced on either build | Fix via the resolved override method (§11 item 2): a phoneme-substitution table fed to `create(..., is_phonemes=True)`. Recorded **separately** from the int8 verdict. **Do not bake into `render_reflexes.py`** (D-4) until names are correct. Carries the design-doc correction (misaki → phoneme table). |
| Override phoneme string contains a non-vocab char (ASCII `'` for IPA `ˈ`, a stray Latin letter) | The Kokoro tokenizer **silently drops** it → truncated phonemes, degenerate audio, no error (confirmed locally, §11 item 4). Validate every override string tokenizes to its expected length before use; rule 5's per-render guard is the backstop. |
| Negotiated shared-mode WASAPI buffer **> 50ms** | Record the honest number (HP14). The §5 audio-output budget is revised, or the built-in device is flagged in the future one-liner — **exclusive mode is NOT adopted** to force ≤50ms (FR-14 violation, §5 rejection). A fat-buffer driver is a documented fact, not a bug to fight. |
| Driver **misreports** capabilities / silent buffer inflation (HP14) | P-4b reads the *negotiated* latency, not the requested one, precisely to catch this. If reported vs actual diverge, record both; the negotiated number is the one the gate reads. |
| Battery changes the negotiated buffer or int8 audibility | Cheap to check; record it. A buffer that only holds ≤50ms on mains is a mains-only claim (the §9 battery-honesty spirit). |
| Rendered A or B is **silent/empty** (espeak-ng path bug, no exception) | Rule 5's per-render non-silence guard: abort the run loudly, record nothing. A silent ABX pair is a false "indistinguishable"; this is the P-2 silent-synthesis class in the ear-check. |
| Selective build missing / quantization utility fails | Fail loudly with the build path; record nothing (a missing run is honest, a fabricated verdict is a lie). `--dry-run` still works offline. |
| No built-in speaker device / PortAudio host-API mismatch | P-4b fails loudly naming the device; do not substitute a Bluetooth/USB device silently — that is a different measurement (§3). |

## 14. Test plan

- **Unit (pure core only, no engine, no audio device):**
  - *Ear probe:* ABX binomial significance on known (correct, total) counts incl. the chance boundary; seeded trial-order + X-assignment is deterministic and reproducible; name-correctness tally over a known response set; gate-branch selection (indistinguishable / distinguishable / **negative-control-failed**); arg-parse defaults + overrides; `--dry-run` exits 0 and prints a ruling block importing no engine.
  - *WASAPI probe:* ms-from-frames/samplerate conversion on known values; ≤50ms gate branch (pass / over-budget); arg-parse; `--dry-run` exits 0 opening no device.
  - *Build utility:* exclusion-list assembly is deterministic; the report/hash formatter is pure and stable.
- **Contract:** none (the §6.3 `TTS` interface and the audio-output stage arrive at M3a; P-4 measures, it does not implement them).
- **Pipeline harness:** none (P-4a renders raw synthesis; P-4b opens a raw `sounddevice` stream — neither is the Pipecat graph).
- **Manual (the measurements themselves):**
  1. Confirm the `uv` venv is Python **3.12**; `models/kokoro-v1.0.onnx`, `kokoro-v1.0.int8.onnx`, and `voices-v1.0.bin` present (they are).
  2. `python scripts/build_kokoro_selective_int8.py` → produces `models/kokoro-v1.0.int8-selective.onnx`; recipe + SHA256 recorded in `docs/p4-int8-build.md`.
  3. In a quiet room, on the real playback path: `python scripts/measure_p4_int8_ear.py --builds fp32,selective,blind --grader waleed` → blind ABX; **confirm the negative control is detectable** before trusting the selective verdict; tally name pronunciations. Repeat with a **second grader** if available.
  4. `python scripts/measure_p4_wasapi.py --device default --label mains` on **built-in speakers** → negotiated buffer/latency vs the 50ms gate; then a **battery** spot-check.
  5. Paste both rulings into `docs/m0-measurements.md`: (a) the ABX result + significance + name-correctness + which build ships + the voice-independence/re-run caveat; (b) the negotiated shared-mode latency in ms + power label + device.

No test writes under `memory/raw/`. No test calls the Claude API. No test imports the TTS engine or opens an audio device.

## 15. Definition of done

Every box, ticked, with evidence:

- [ ] Milestone exit test (design §7 M0): **both P-4 sub-gates ruled and recorded** — (a) the **blind ABX** int8-vs-fp32 result with its **binomial significance**, the **negative-control** result, **name-pronunciation correctness**, which build ships, thread count, and the **voice-independence + P-6-re-run** caveat; (b) the **negotiated shared-mode WASAPI buffer/latency in ms** vs the 50ms gate, with **device name and power label**
- [ ] `python .claude/hooks/invariant_lint.py --full` clean
- [ ] `pytest -q` green (ABX stats + gate-branch + name-tally + ms-conversion + arg-parse unit tests; no engine, no device, no network)
- [ ] No session written by this code (it writes none) — schema check trivially holds; confirmed no `memory/raw/` write
- [ ] `spec-guardian` run; BLOCKING findings resolved
- [ ] `latency-auditor` run — P-4b feeds the §5 audio-output budget and P-4a gates the build the TTS-first-audio budget names; the "buffer ≠ acoustic path" and "quality gate ≠ latency gate" distinctions (§6) are exactly what it audits
- [ ] `security-review` — trivially clean (no credentials, no egress, no subprocess; local synthesis + local audio device only; confirm the produced build and any name-bearing corpus render honour the P-3 git-ignore split — `docs/p3-vocab-seed.txt` and any name-bearing audio stay local)
- [ ] `docs/p4-int8-build.md` written — the selective build's exclusion recipe + SHA256 (silent-drift guard for the produced artifact)
- [ ] Both P-4 rulings written into `docs/m0-measurements.md` (replacing the pending stub)
- [ ] Probe defaults documented in `--help`; the downstream `speech.tts.model_build` and `audio.output.exclusive` decisions noted for M3a; no setting in any tracked runtime file
- [ ] **Usable that evening** — trivially met; the probes leave the runtime untouched
- [ ] Build-plan P-4 checkbox ticked (only when **both** sub-gates rule); M0 note written

## 16. Out of scope

- **The int8 *speed* delta (P-2).** P-4a grades whether int8 sounds like fp32; the RTF/speed of the int8 build is P-2's `--build quantized` rung. P-4 judges quality only.
- **Voice identity selection (P-6).** P-4a uses the config-default voice; the int8 verdict is voice-independent, but the ear test is **re-run on the P-6 winner** (rule 4). Which voice *is* Malang is P-6's blind-ranked gate.
- **Building `render_reflexes.py` and the reflex clip set (D-4, M2).** P-4 confirms names are *sayable* and which build ships; regenerating clips from the phrase list is M2 work, gated on P-4's name-correctness result.
- **Micro-first-chunk / clause-joint prosody and first-audio latency (M3a, D-10, HP16).** P-4 does the **int8** half of HP13; the clause-joint seams, crossfades, and the 300ms first-micro-chunk number are M3a with the real pipeline.
- **The FR-18 name post-corrector (STT side).** P-4 is *pronunciation* (TTS output); FR-18 is *recognition* (STT input). Same shared vocab list, opposite ends (§3).
- **Correcting the design doc's "misaki lexicon" wording (a doc fix, tracked separately).** P-4 *surfaces* that the onnx runtime uses a phoneme-substitution table + `is_phonemes=True`, not misaki (§11 item 2, docs-researcher-confirmed); editing design §2 and the persona to match is a documentation change owned outside this spec — P-4 does not silently work around it, and does not itself rewrite those docs.
- **End-to-end perceived acoustic output latency (HP10, M3a/M3b).** P-4b measures the API/driver output buffer, not the phone-recorded speaker-to-ear gap.
- **Exclusive-mode WASAPI.** Rejected as default (§5); a strictly opt-in config path evaluated only if a device forces it — not measured here.
- **Sustained full-stack duplex load (P-5).** P-4 renders/plays in isolation; int8 audibility and buffer stability under the full resident stack (AEC + Silero + smart-turn + Moonshine + recorder + fsyncing Scribe) is P-5.
- Anything that reads from `memory/`.
