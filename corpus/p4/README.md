# corpus/p4 — the P-4a ear-check corpus

The blind-ABX ear check (`scripts/measure_p4_int8_ear.py`) grades selective-int8
vs fp32 Kokoro on ten emotionally-varied sentences that include "Malang" and real
family names (HP13: int8 flattens emotional timbre first; names are load-bearing
for D-4's reflex clips).

## Files

| File | Tracked? | What |
|---|---|---|
| `corpus_template.txt` | **yes** | The 10 sentences, with `{NAME1}`/`{NAME2}` placeholders. No real names. |
| `names.example.txt` | **yes** | The format, with fictional example names. |
| `names.txt` | **NO — git-ignored** | *You* author this locally: real family names + IPA overrides. |

## Why names.txt is local (spec §12 rule 3 / B-1)

The owner decision of 2026-08-02 keeps real family/friend names off GitHub (same as
the P-3 vocab seed). A byte-stable corpus baked into a tracked script *is* the leak
that decision exists to prevent. So: the template is tracked, the names are local,
and the corpus is reconstructed at run time. Pin `names.txt`'s SHA256 in
`docs/p4-int8-build.md` when you run the ear check, so a re-run proves the same
corpus was graded.

## To run

1. `cp corpus/p4/names.example.txt corpus/p4/names.txt` and fill in real names.
   For each name whose default espeak-ng pronunciation is wrong, add an IPA
   override (use the real stress mark `ˈ` = U+02C8, not an ASCII apostrophe — the
   Kokoro tokenizer silently drops non-vocab characters).
2. `uv run python scripts/measure_p4_int8_ear.py --grader <you>` in a quiet room,
   on the real playback path. Confirm the negative control (blind int8) is
   *detectable* before trusting the selective verdict.
