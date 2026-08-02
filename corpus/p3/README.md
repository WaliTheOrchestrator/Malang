# P-3 corpus

The hand-corrected reference speech that the P-3 STT bake-off measures against
(`scripts/measure_p3_stt.py`). See `prompts.md` for what to record.

## Layout

```
corpus/p3/
  prompts.md        what to record, and why (three registers)
  manifest.json     entries: id, register, wav, reference, proper_nouns[]
  reference/        hand-corrected ground-truth transcripts
                    (monologue.txt + codeswitch.txt GIT-IGNORED — contain names;
                     read.txt tracked — no names)
  manifest.json     entries + proper_noun tags (GIT-IGNORED — contains names)
  audio/            the recorded WAVs (GIT-IGNORED — your voice, not code)
  model-hashes.md   pinned weight revisions + SHA256 (written by fetch_p3_models.py)
```

## Provenance / privacy

- **`audio/*.wav` is git-ignored** (the global `*.wav` rule). ~4 min of the owner's
  voice is personal data; the record's sacredness lives in `memory/`, not in test
  fixtures. The **filled references + manifest + seed vocab are ALSO git-ignored**
  (2026-08-02 owner decision) because they carry real family/friend names — only the
  name-free code, schema, `prompts.md`, and this README are tracked.
- Record on the **production mic**. A corpus recorded on another device is a
  different measurement (accent + room + mic all shape WER).

## Speaker notes (affect how WER is read)

- **/f/ ↔ /p/ substitution.** The speaker sometimes realizes /f/ as /p/ (says "p"
  where a word has "f") — a common Pashto/Urdu-influenced substitution. So a subset
  of the substitution "errors" in the transcripts are **faithful transcriptions of
  what was actually pronounced**, not model failures (e.g. `full`→`pull`, or a name
  containing /f/ heard with a /p/). Weigh this on any proper noun containing f/p
  before reading a high name-error as a model weakness. This is a real property of the
  durable record and exactly the kind of thing the FR-18 lexicon will later need.

## Model pins

Downloaded by `python scripts/fetch_p3_models.py` into `models/` (git-ignored),
each at a fixed revision, with SHA256 recorded in **`model-hashes.md`** — verify
those before trusting a re-run (spec section 13 silent-drift guard; the Moonshine
CDN has no upstream version tag, so the hash is its only pin).

- Parakeet TDT 0.6B v3 — HF `istupakov/parakeet-tdt-0.6b-v3-onnx` @ `8f23f0c…` — **CC-BY-4.0** (attribution in `/NOTICE`).
- whisper-large-v3-turbo (CT2) — HF `deepdml/faster-whisper-large-v3-turbo-ct2` @ `4df90f7…` — MIT.
- Moonshine v2 small+medium (en) — Moonshine AI CDN via `moonshine-voice` — MIT.

## Running

```
python scripts/record_p3_corpus.py                 # record (needs --extra recorder)
# ...hand-correct reference/*.txt, tag proper_nouns in manifest.json...
python scripts/measure_p3_stt.py --corpus corpus/p3 --models all
```
