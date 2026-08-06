# P-4 selective-int8 Kokoro build

Provenance for the SELECTIVE int8 build the P-4a ear check grades. This is
the CANDIDATE; `models/kokoro-v1.0.int8.onnx` (the blind off-the-shelf build)
is the negative control. Regenerate with
`scripts/build_kokoro_selective_int8.py`; re-verify by ear after any model or
runtime change (CLAUDE.md rule 4, HP13).

- **Built:** 2026-08-04T12:33:05+05:00
- **Source (fp32):** `models/kokoro-v1.0.onnx`  (310.5 MiB)
    - SHA256 `7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5`
- **Output (selective int8):** `models/kokoro-v1.0.int8-selective.onnx`  (87.7 MiB)
    - SHA256 `f57cb0c5b15e1b42855e085f7b31cf29ff1f4beefa06c4aed0adf80dc1f2e46a`
- **Quantizer:** onnxruntime `quantize_dynamic`, weight_type=QInt8, per_channel=False
- **Exclude regex:** `conv_post/Conv`  (resolved to 1 node(s))
- **Nodes kept in fp32 (excluded from quantization):**
  - `/decoder/decoder/generator/conv_post/Conv`

## Why this node, and the export-name caveat (spec §11 item 1)

The ISTFTNet vocoder's final post-conv is the one node blind dynamic
quantization turns to audible static (adrianlyjak's per-node listening
methodology; a mel-distance metric missed it - HP16's "no metric catches
it"). LayerNorm/InstanceNorm need no explicit exclusion (ORT's dynamic
quantizer does not target those op types).

**Export-specific node names:** the spec's assumed pattern
`^/decoder/generator/conv_post/Conv` matches ZERO nodes in this export -
`kokoro-v1.0.onnx` uses a double `/decoder/decoder/generator/` prefix. The
default `--exclude` regex is the prefix-robust suffix `conv_post/Conv`, and
the build ABORTS on zero matches rather than emit a silently-blind build.

## Ear-check names file (filled at P-4a run time)

The blind-ABX corpus injects real family names from a git-ignored local file
(`corpus/p4/names.txt`; see `corpus/p4/README.md`). Pin its SHA256 here when
the ear check runs, so a re-run proves the SAME corpus was graded (spec §12
rule 3). Left blank until the first P-4a run:

- **`corpus/p4/names.txt` SHA256:** `52c626be0eac2c43c5cbe027fc2a21be22127126a9409cbf6abff5d7877d8406` (graded 2026-08-06)
