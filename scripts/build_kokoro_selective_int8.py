#!/usr/bin/env python3
"""P-4 build utility: produce the SELECTIVE int8 Kokoro build (the candidate).

Spec: .claude/specs/p-4-selective-int8-ear-check-wasapi-probe.md (§9, §11 item 1).

HP16 says a blind `quantize_dynamic` of Kokoro yields "audible static" - the
off-the-shelf models/kokoro-v1.0.int8.onnx is exactly that blind build and is the
NEGATIVE CONTROL, never the ship candidate. This one-time utility produces the
*selective* build the P-4a ear check actually grades: int8 everywhere EXCEPT the
ISTFTNet vocoder's final post-conv, which is kept in fp32. adrianlyjak's public
per-node methodology flagged that node BY EAR after an automated mel-distance
metric missed it - a live instance of HP16 ("no metric catches it").

    uv run python scripts/build_kokoro_selective_int8.py
    uv run python scripts/build_kokoro_selective_int8.py --dry-run   # no onnx, exercises the report

Node names are EXPORT-SPECIFIC (spec §11 caveat). This script `onnx.load()`s the
actual model and resolves the --exclude REGEX against the real node names; if it
matches nothing it ABORTS rather than silently emitting a fully-blind build. On
this export the vocoder post-conv is `/decoder/decoder/generator/conv_post/Conv`
(a DOUBLE `/decoder/decoder/` prefix - the spec's assumed `^/decoder/generator/`
pattern would have matched zero nodes, which is precisely why we confirm first).

`quantize_dynamic` takes node NAMES (not op types) in `nodes_to_exclude`, so the
regex is resolved to concrete names here. LayerNorm/InstanceNorm need no explicit
exclusion - ORT's dynamic quantizer does not target those op types by default.

The `onnx` / `onnxruntime.quantization` imports are lazy (inside the engine layer)
so the pure core, --dry-run, and the unit tests need nothing installed. `onnx` is
NOT bundled with the onnxruntime CPU wheel; it lives in the `build` extra
(spec §11). This is a build-time tool, never imported by runtime speech/tts.py.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import re
import sys

# The vocoder post-conv, kept in fp32 (spec §11 item 1). A suffix regex, so it
# survives this export's double `/decoder/decoder/generator/` prefix.
DEFAULT_EXCLUDE = r"conv_post/Conv"
DEFAULT_FP32 = "models/kokoro-v1.0.onnx"
DEFAULT_OUT = "models/kokoro-v1.0.int8-selective.onnx"
DEFAULT_REPORT = "docs/p4-int8-build.md"


# --------------------------------------------------------------------------- #
# Pure core - no onnx, unit-tested.
# --------------------------------------------------------------------------- #
def matching_node_names(node_names, pattern):
    """Every node name matching `pattern` (a regex, `re.search` semantics).

    Returned in input order. Empty means the pattern matched nothing - the
    caller MUST treat that as a hard error (a blind build masquerading as
    selective is the exact failure HP16 warns about).
    """
    rx = re.compile(pattern)
    return [n for n in node_names if rx.search(n)]


def sha256_file(path, _chunk=1 << 20):
    """Streamed SHA256 of a file, hex. The silent-drift guard for a produced
    artifact - a future re-run proves it graded the SAME build (spec §12 rule 3)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_chunk), b""):
            h.update(block)
    return h.hexdigest()


def _mib(n_bytes):
    return None if n_bytes is None else n_bytes / (1024 * 1024)


def format_build_report(meta):
    """The docs/p4-int8-build.md provenance note. Pure; ready to write to disk."""
    excl = meta.get("excluded_nodes") or []
    excl_block = "\n".join(f"  - `{n}`" for n in excl) or "  - (none - DRY RUN)"
    src_mib = _mib(meta.get("src_bytes"))
    out_mib = _mib(meta.get("out_bytes"))

    def sz(v):
        return "n/a" if v is None else f"{v:.1f} MiB"

    lines = [
        "# P-4 selective-int8 Kokoro build",
        "",
        "Provenance for the SELECTIVE int8 build the P-4a ear check grades. This is",
        "the CANDIDATE; `models/kokoro-v1.0.int8.onnx` (the blind off-the-shelf build)",
        "is the negative control. Regenerate with",
        "`scripts/build_kokoro_selective_int8.py`; re-verify by ear after any model or",
        "runtime change (CLAUDE.md rule 4, HP13).",
        "",
        f"- **Built:** {meta.get('date', 'n/a')}",
        f"- **Source (fp32):** `{meta.get('src_path')}`  ({sz(src_mib)})",
        f"    - SHA256 `{meta.get('src_sha', 'n/a')}`",
        f"- **Output (selective int8):** `{meta.get('out_path')}`  ({sz(out_mib)})",
        f"    - SHA256 `{meta.get('out_sha', 'n/a')}`",
        f"- **Quantizer:** onnxruntime `quantize_dynamic`, weight_type=QInt8, "
        f"per_channel={meta.get('per_channel', False)}",
        f"- **Exclude regex:** `{meta.get('exclude_pattern')}`  "
        f"(resolved to {len(excl)} node(s))",
        "- **Nodes kept in fp32 (excluded from quantization):**",
        excl_block,
        "",
        "## Why this node, and the export-name caveat (spec §11 item 1)",
        "",
        "The ISTFTNet vocoder's final post-conv is the one node blind dynamic",
        "quantization turns to audible static (adrianlyjak's per-node listening",
        "methodology; a mel-distance metric missed it - HP16's \"no metric catches",
        "it\"). LayerNorm/InstanceNorm need no explicit exclusion (ORT's dynamic",
        "quantizer does not target those op types).",
        "",
        "**Export-specific node names:** the spec's assumed pattern",
        "`^/decoder/generator/conv_post/Conv` matches ZERO nodes in this export -",
        "`kokoro-v1.0.onnx` uses a double `/decoder/decoder/generator/` prefix. The",
        "default `--exclude` regex is the prefix-robust suffix `conv_post/Conv`, and",
        "the build ABORTS on zero matches rather than emit a silently-blind build.",
        "",
        "## Ear-check names file (filled at P-4a run time)",
        "",
        "The blind-ABX corpus injects real family names from a git-ignored local file",
        "(`corpus/p4/names.txt`; see `corpus/p4/README.md`). Pin its SHA256 here when",
        "the ear check runs, so a re-run proves the SAME corpus was graded (spec §12",
        "rule 3). Left blank until the first P-4a run:",
        "",
        "- **`corpus/p4/names.txt` SHA256:** _(fill at ear-check time)_",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="build_kokoro_selective_int8.py",
        description="P-4: build the selective-int8 Kokoro candidate (vocoder post-conv kept fp32).",
    )
    p.add_argument("--fp32", default=DEFAULT_FP32,
                   help="Source fp32 model (default: %(default)s).")
    p.add_argument("--out", default=DEFAULT_OUT,
                   help="Output selective-int8 model (default: %(default)s).")
    p.add_argument("--exclude", default=DEFAULT_EXCLUDE,
                   help="Regex (re.search) of node names kept in fp32 "
                        "(default: %(default)r - the vocoder post-conv).")
    p.add_argument("--per-channel", action="store_true",
                   help="Per-channel weight quantization (default off).")
    p.add_argument("--report", default=DEFAULT_REPORT,
                   help="Where to write the build provenance note (default: %(default)s).")
    p.add_argument("--dry-run", action="store_true",
                   help="Offline: exercise the report formatter, import no onnx.")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- #
# Engine layer - hand-run only, lazily imports onnx / onnxruntime.quantization.
# --------------------------------------------------------------------------- #
def load_node_names(fp32_path):
    """The graph's node names, without materialising external weight data."""
    import onnx
    model = onnx.load(fp32_path, load_external_data=False)
    return [n.name for n in model.graph.node]


def build_selective(fp32_path, out_path, exclude_names, per_channel):
    """Run ORT dynamic quantization, excluding `exclude_names` (kept fp32)."""
    from onnxruntime.quantization import quantize_dynamic, QuantType
    quantize_dynamic(
        model_input=fp32_path,
        model_output=out_path,
        nodes_to_exclude=list(exclude_names),
        weight_type=QuantType.QInt8,
        per_channel=per_channel,
    )


def _run_dry():
    meta = {
        "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "src_path": DEFAULT_FP32, "src_sha": "<dry-run>", "src_bytes": 325 * 1024 * 1024,
        "out_path": DEFAULT_OUT, "out_sha": "<dry-run>", "out_bytes": 90 * 1024 * 1024,
        "exclude_pattern": DEFAULT_EXCLUDE, "per_channel": False,
        "excluded_nodes": ["/decoder/decoder/generator/conv_post/Conv (example)"],
    }
    print("[dry-run] no onnx loaded, no model written. Report preview:\n")
    print(format_build_report(meta))
    return 0


def _run_live(args):
    if not os.path.exists(args.fp32):
        print(f"Missing source model: {args.fp32}\n"
              "Download kokoro-v1.0.onnx from the thewh1teagle/kokoro-onnx "
              "model-files-v1.0 release into models/. Building nothing.",
              file=sys.stderr)
        return 1

    try:
        node_names = load_node_names(args.fp32)
    except ImportError as exc:
        print(f"onnx is not installed ({exc}). It is NOT bundled with onnxruntime; "
              "install the build extra: `uv pip install 'onnx>=1.22,<2'`. "
              "--dry-run works offline.", file=sys.stderr)
        return 2

    excluded = matching_node_names(node_names, args.exclude)
    if not excluded:
        print(f"ABORT: --exclude regex {args.exclude!r} matched ZERO of "
              f"{len(node_names)} node names in {args.fp32}.\n"
              "A quantize with an empty exclusion set is a BLIND build (HP16: audible "
              "static), which must never masquerade as the selective candidate. Node "
              "names are export-specific (spec §11 caveat) - inspect the graph and fix "
              "the regex. Building nothing.", file=sys.stderr)
        return 1

    print(f"Excluding {len(excluded)} node(s) from int8 (kept fp32):")
    for n in excluded:
        print(f"    {n}")

    try:
        build_selective(args.fp32, args.out, excluded, args.per_channel)
    except ImportError as exc:
        print(f"onnxruntime.quantization unavailable ({exc}). Install the build extra "
              "(`onnx`). Building nothing.", file=sys.stderr)
        return 2

    src_bytes = os.path.getsize(args.fp32)
    out_bytes = os.path.getsize(args.out)
    meta = {
        "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "src_path": args.fp32, "src_sha": sha256_file(args.fp32), "src_bytes": src_bytes,
        "out_path": args.out, "out_sha": sha256_file(args.out), "out_bytes": out_bytes,
        "exclude_pattern": args.exclude, "per_channel": args.per_channel,
        "excluded_nodes": excluded,
    }
    report = format_build_report(meta)
    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)

    print(f"\nWrote {args.out} ({_mib(out_bytes):.1f} MiB, "
          f"from {_mib(src_bytes):.1f} MiB fp32).")
    print(f"Provenance written to {args.report} (SHA256 recorded).")
    print("This is the SELECTIVE candidate. Grade it by ear against fp32 with "
          "scripts/measure_p4_int8_ear.py; the blind kokoro-v1.0.int8.onnx is the "
          "negative control.")
    return 0


def main(argv):
    args = parse_args(argv)
    if args.dry_run:
        return _run_dry()
    return _run_live(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
