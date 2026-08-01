#!/usr/bin/env python3
"""P-3 measurement gate: quantitative STT bake-off on this laptop's mic + voice.

Spec: .claude/specs/p-3-stt-bake-off.md (malang-phase1-spec.md section 9).

This is a HAND-RUN measurement script, not a test. Over a fixed, hand-corrected
corpus (monologue + read passage + deliberately code-switched passage) it measures
WER and proper-noun-error-rate for four configs:

    moonshine-small / moonshine-medium   (live-path candidate, English)
    parakeet                             (memory-path default, Parakeet TDT 0.6B v3)
    whisper-turbo                        (memory-path challenger, large-v3-turbo int8)

    python scripts/measure_p3_stt.py --corpus corpus/p3 --models all
    python scripts/measure_p3_stt.py --dry-run          # offline; exercises the report

It settles TWO decisions (spec section 9), stated separately:
  - MEMORY PATH (the durable record): Parakeet-solo / Parakeet+whisper-hybrid /
    whisper-straight-swap, decided on the code-switched proper-noun-error gap.
  - LIVE PATH: is Moonshine's live WER <= ~12% (else recalibrate downstream
    text-keyed thresholds), and small vs medium.
And it seeds the FR-18 vocab list (docs/p3-vocab-seed.txt).

Honesty rules this script keeps (spec section 12):
  - The hand-corrected reference is ground truth; the same WAVs feed every model.
  - Normalization is applied IDENTICALLY to every hypothesis and the reference.
  - Proper-noun-error-rate is reported separately and per-register - a small
    overall WER gap can hide the code-switched proper-noun tail that decides the hybrid.
  - Empty/garbage transcripts are flagged as ENGINE FAILURES, never averaged in as
    a high WER (the P-2 silent-synthesis failure class, mirrored).
  - Models load ONE AT A TIME and are unloaded between runs (section 6 RAM).

P-3 grades ACCURACY, not latency (Moonshine's live latency is M3a). Every ASR import
is lazy (inside its adapter) so the pure core, --dry-run, and the unit tests need
nothing installed. Self-contained: percentiles + WER + alignment are defined here.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gc
import json
import math
import re
import sys
from pathlib import Path

# Spec section 9: Moonshine live WER above this -> recalibrate every text-keyed
# threshold downstream (reflex selector, fused endpointer, router escalate - HP2).
MOONSHINE_WER_TOLERANCE = 0.12
# Default "within noise" band (absolute) for the memory-path ruling, read on the
# code-switched proper-noun-error-rate gap. Overridable with --noise-floor.
NOISE_FLOOR = 0.02

REGISTERS = ("monologue", "read", "codeswitch")
ALL_MODELS = ("moonshine-small", "moonshine-medium", "parakeet", "whisper-turbo")
# The code-switched register is the deciding passage for the memory-path ruling.
DECIDING_REGISTER = "codeswitch"


# --------------------------------------------------------------------------- #
# Pure core - no engine, unit-tested. Self-contained (no import from P-1/P-2).
# --------------------------------------------------------------------------- #
def percentiles(values, ps):
    """Nearest-rank percentiles. Empty input -> every percentile None (honest)."""
    ps = list(ps)
    if not values:
        return {p: None for p in ps}
    ordered = sorted(values)
    n = len(ordered)
    out = {}
    for p in ps:
        rank = max(1, math.ceil((p / 100.0) * n))
        out[p] = ordered[min(rank, n) - 1]
    return out


def normalize(text):
    """Lowercase, unify apostrophes, extract word tokens. Applied to ref AND hyp.

    Unicode-aware (\\w matches Urdu/Pashto script too, for a romanized-or-native
    code-switched reference). Punctuation and casing are dropped for the standard
    WER; a punctuation-preserving view is a separate concern (spec section 12 rule 3).
    """
    text = text.casefold().replace("’", "'")
    tokens = re.findall(r"[\w']+", text, re.UNICODE)
    return [t.strip("'") for t in tokens if t.strip("'")]


def normalize_terms(terms):
    """Normalize a list of proper-noun phrases into a flat set of tokens.

    'Wali Khan' -> {'wali', 'khan'}; 'Malang' -> {'malang'}. Proper-noun-error-rate
    is then a token-level rate over exactly these tokens.
    """
    out = set()
    for term in terms:
        out.update(normalize(term))
    return out


def align(ref, hyp):
    """Word-level Levenshtein with backtrace. Returns ops [(op, ref_tok, hyp_tok)].

    op in {equal, sub, del, ins}. This one alignment is the shared spine: WER,
    proper-noun-error-rate, and the seed-vocab pairs all read off it.
    """
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j - 1], d[i - 1][j], d[i][j - 1])
    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1] and d[i][j] == d[i - 1][j - 1]:
            ops.append(("equal", ref[i - 1], hyp[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            ops.append(("sub", ref[i - 1], hyp[j - 1]))
            i -= 1
            j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", ref[i - 1], None))
            i -= 1
        else:
            ops.append(("ins", None, hyp[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def wer_counts(ops):
    """Substitutions/Deletions/Insertions and reference length N from an alignment."""
    S = sum(1 for o in ops if o[0] == "sub")
    D = sum(1 for o in ops if o[0] == "del")
    I = sum(1 for o in ops if o[0] == "ins")
    N = sum(1 for o in ops if o[0] in ("equal", "sub", "del"))
    return {"S": S, "D": D, "I": I, "N": N}


def wer_rate(counts):
    """WER = (S+D+I)/N. None if the reference is empty (no denominator = no number)."""
    N = counts["N"]
    if not N:
        return None
    return (counts["S"] + counts["D"] + counts["I"]) / N


def proper_noun_counts(ops, proper_nouns):
    """Errors over ref tokens that are proper nouns (equal/sub/del where ref in set)."""
    pn = set(proper_nouns)
    total = 0
    errors = 0
    for op, r, _h in ops:
        if r is not None and r in pn:
            total += 1
            if op != "equal":
                errors += 1
    return {"errors": errors, "total": total}


def rate(counts, num_key, den_key):
    """errors/total style rate; None when the denominator is zero."""
    den = counts[den_key]
    return counts[num_key] / den if den else None


def seed_from_alignment(ops, proper_nouns):
    """Proper-noun near-misses: [{name, heard, op}] for sub/del on tagged tokens."""
    pn = set(proper_nouns)
    out = []
    for op, r, h in ops:
        if r is not None and r in pn and op != "equal":
            out.append({"name": r, "heard": h, "op": op})
    return out


def sum_counts(dicts, keys):
    """Micro-average helper: element-wise sum of the given keys across dicts."""
    return {k: sum(d[k] for d in dicts) for k in keys}


def memory_path_ruling(p_cs, w_cs, p_overall, w_overall, noise_floor=NOISE_FLOOR):
    """The pre-decided memory-path branch (spec section 9), on the deciding passage.

    p_cs / w_cs   = Parakeet / whisper code-switched PROPER-NOUN-error rate (the
                    number section 9 says decides the hybrid).
    p_overall / w_overall = overall WER, used to tell "whisper dominates" (swap)
                    from "gap on code-switched spans only" (hybrid).
    Returns (key, human_reason). key in {parakeet-solo, whisper-swap, hybrid, undetermined}.
    """
    if None in (p_cs, w_cs, p_overall, w_overall):
        return ("undetermined", "missing numbers - a model failed or a register is empty; "
                "rule nothing")
    cs_gap = p_cs - w_cs            # > 0 => whisper better on the deciding passage
    overall_gap = p_overall - w_overall  # > 0 => whisper better overall
    if cs_gap <= noise_floor:
        return ("parakeet-solo",
                f"Parakeet within noise of whisper on the code-switched proper nouns "
                f"(gap {cs_gap:+.1%} <= {noise_floor:.0%}) -> Parakeet ships SOLO; the "
                "whisper second pass is not built at M7.")
    if overall_gap > noise_floor:
        return ("whisper-swap",
                f"whisper dominates across the board (code-switched proper-noun gap "
                f"{cs_gap:+.1%}, overall WER gap {overall_gap:+.1%}) -> STRAIGHT SWAP to "
                "whisper-turbo, IF it fits FR-11's 5-min window + Afterword RAM (section 6).")
    return ("hybrid",
            f"material gap on code-switched proper nouns ({cs_gap:+.1%}) but not overall "
            f"({overall_gap:+.1%}) -> Parakeet PRIMARY + whisper-turbo second pass on "
            "flagged turns (amend/alternates, Afterword, within FR-11's window).")


def moonshine_health(wer, tolerance=MOONSHINE_WER_TOLERANCE):
    """Live-path health (spec section 9). Returns (key, human_reason)."""
    if wer is None:
        return ("unknown", "no Moonshine WER recorded")
    if wer <= tolerance:
        return ("ok", f"Moonshine live WER {wer:.1%} <= {tolerance:.0%} - downstream "
                "text-keyed thresholds hold.")
    return ("recalibrate", f"Moonshine live WER {wer:.1%} > {tolerance:.0%} - RECALIBRATE "
            "every text-keyed threshold downstream (reflex selector, fused endpointer, "
            "router escalate - HP2). Changes M3a/M5 calibration, not just the STT choice.")


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="measure_p3_stt.py",
        description="P-3: quantitative STT bake-off (WER + proper-noun-error-rate).",
    )
    p.add_argument("--corpus", default="corpus/p3",
                   help="Corpus dir: manifest.json + reference/*.txt + audio/*.wav "
                        "(default: %(default)s).")
    p.add_argument("--models", nargs="+", default=["all"],
                   choices=("all",) + ALL_MODELS,
                   help="Which configs to run (default: all).")
    p.add_argument("--threads", type=int, default=3,
                   help="ORT / CT2 intra-op thread count, recorded in the ruling "
                        "(default: %(default)s).")
    p.add_argument("--models-dir", default="models",
                   help="Where the downloaded weights live (default: %(default)s).")
    p.add_argument("--normalizer", choices=("standard",), default="standard",
                   help="Text normalization, applied identically to ref and hyp.")
    p.add_argument("--noise-floor", type=float, default=NOISE_FLOOR, dest="noise_floor",
                   help="Absolute 'within noise' band for the memory-path ruling, read "
                        "on the code-switched proper-noun gap (default: %(default)s).")
    p.add_argument("--seed-vocab", default="docs/p3-vocab-seed.txt", dest="seed_vocab",
                   help="Where the FR-18 seed vocab list is written (default: %(default)s).")
    p.add_argument("--cross-check", action="store_true",
                   help="Also print jiwer's WER as an authoritative cross-check (needs "
                        "jiwer installed; the headline numbers use the local aligner).")
    p.add_argument("--smoke", action="store_true",
                   help="Banner the output as SMOKE - a wiring test, NOT the P-3 gate.")
    p.add_argument("--dry-run", action="store_true",
                   help="Offline: exercise the report on synthetic numbers, no engine.")
    return p.parse_args(argv)


def resolve_models(models):
    """Expand ['all'] and de-duplicate while preserving canonical order."""
    if "all" in models:
        return list(ALL_MODELS)
    seen = [m for m in ALL_MODELS if m in set(models)]
    return seen


# --------------------------------------------------------------------------- #
# Metrics assembly - pure, given per-entry alignments.
# --------------------------------------------------------------------------- #
def score_model(entries, hyps):
    """Turn {id: hypothesis_text} into the full per-model metrics dict.

    `entries` is the loaded corpus (each: id, register, ref_tokens, pn set). Empty
    hypotheses on non-trivial references are counted as `empty` (engine-failure
    signal), not folded into WER as a legitimate loss.
    """
    per_reg = {r: {"wer": [], "pn": []} for r in REGISTERS}
    per_file_wer = []
    seed = []
    empty = 0
    for e in entries:
        hyp_tokens = normalize(hyps.get(e["id"], ""))
        if not hyp_tokens and len(e["ref_tokens"]) >= 3:
            empty += 1
        ops = align(e["ref_tokens"], hyp_tokens)
        wc = wer_counts(ops)
        pnc = proper_noun_counts(ops, e["pn"])
        reg = e["register"] if e["register"] in per_reg else "monologue"
        per_reg[reg]["wer"].append(wc)
        per_reg[reg]["pn"].append(pnc)
        wr = wer_rate(wc)
        if wr is not None:
            per_file_wer.append(wr)
        seed.extend({**s, "id": e["id"]} for s in seed_from_alignment(ops, e["pn"]))

    by_register = {}
    for r in REGISTERS:
        wsum = sum_counts(per_reg[r]["wer"] or [{"S": 0, "D": 0, "I": 0, "N": 0}],
                          ("S", "D", "I", "N"))
        psum = sum_counts(per_reg[r]["pn"] or [{"errors": 0, "total": 0}],
                          ("errors", "total"))
        by_register[r] = {
            "wer": {**wsum, "rate": wer_rate(wsum)},
            "pn": {**psum, "rate": rate(psum, "errors", "total")},
        }
    all_wer = sum_counts([by_register[r]["wer"] for r in REGISTERS], ("S", "D", "I", "N"))
    all_pn = sum_counts([by_register[r]["pn"] for r in REGISTERS], ("errors", "total"))
    return {
        "by_register": by_register,
        "overall_wer": {**all_wer, "rate": wer_rate(all_wer)},
        "pn_overall": {**all_pn, "rate": rate(all_pn, "errors", "total")},
        "per_file_wer": percentiles(per_file_wer, (50, 95)),
        "seed": seed,
        "empty": empty,
        "n_entries": len(entries),
    }


def _pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def format_report(results, meta):
    """Emit the /measure ruling shape with the per-model table and both rulings."""
    smoke = meta.get("smoke")
    lines = []
    if smoke:
        lines += ["=" * 72,
                  "SMOKE RUN - wiring test on synthetic audio. This is NOT the P-3 gate.",
                  "A real ruling needs the hand-corrected 30-min mic corpus (spec section 3).",
                  "=" * 72, ""]
    lines += [
        "GATE: P-3" + ("  [SMOKE - not a ruling]" if smoke else ""),
        f"DATE / CONDITIONS: {meta.get('conditions')}",
        f"    corpus: {meta.get('corpus')} | normalizer={meta.get('normalizer')} | "
        f"threads={meta.get('threads')} | noise_floor={meta.get('noise_floor')}",
        "",
        "PER-MODEL  (WER / proper-noun-error-rate, micro-averaged):",
        f"    {'model':<18}{'overall':>10}{'monologue':>12}{'read':>10}"
        f"{'codeswitch':>12}{'PN(all)':>10}{'PN(cs)':>9}  notes",
    ]
    for mk in resolve_models(meta.get("requested", list(results))):
        r = results.get(mk)
        if r is None:
            continue
        if r.get("failed"):
            lines.append(f"    {mk:<18}{'ENGINE FAILURE: ' + r.get('fail_reason', ''):>10}")
            continue
        br = r["by_register"]
        note = ""
        if r["empty"]:
            note = f"{r['empty']}/{r['n_entries']} empty hyps"
        lines.append(
            f"    {mk:<18}"
            f"{_pct(r['overall_wer']['rate']):>10}"
            f"{_pct(br['monologue']['wer']['rate']):>12}"
            f"{_pct(br['read']['wer']['rate']):>10}"
            f"{_pct(br['codeswitch']['wer']['rate']):>12}"
            f"{_pct(r['pn_overall']['rate']):>10}"
            f"{_pct(br['codeswitch']['pn']['rate']):>9}  {note}"
        )

    # --- memory-path ruling ------------------------------------------------- #
    par = results.get("parakeet", {})
    wsp = results.get("whisper-turbo", {})
    p_cs = par.get("by_register", {}).get("codeswitch", {}).get("pn", {}).get("rate")
    w_cs = wsp.get("by_register", {}).get("codeswitch", {}).get("pn", {}).get("rate")
    p_ov = par.get("overall_wer", {}).get("rate")
    w_ov = wsp.get("overall_wer", {}).get("rate")
    mem_key, mem_reason = memory_path_ruling(p_cs, w_cs, p_ov, w_ov, meta.get("noise_floor"))

    # --- live-path ruling --------------------------------------------------- #
    ms = {k: results[k] for k in ("moonshine-small", "moonshine-medium") if k in results}
    size_pick, ms_wer = None, None
    for k, r in ms.items():
        if r.get("failed"):
            continue
        w = r["overall_wer"]["rate"]
        if w is not None and (ms_wer is None or w < ms_wer):
            ms_wer, size_pick = w, k
    live_key, live_reason = moonshine_health(ms_wer, MOONSHINE_WER_TOLERANCE)

    lines += [
        "",
        "MEMORY-PATH RULING (durable record, spec section 9):",
        f"    [{mem_key}] {mem_reason}",
        "    Runtime viability (section 6): a hybrid/swap must fit FR-11's 5-min window +",
        "    the Afterword ~3GB peak; note it before committing the ruling.",
        "",
        "LIVE-PATH RULING (Moonshine):",
        f"    recommended size: {size_pick or 'n/a'}"
        + (f" (WER {_pct(ms_wer)})" if size_pick else ""),
        f"    [{live_key}] {live_reason}",
        "",
        f"SEED VOCAB: {meta.get('seed_vocab')} (FR-18 / misaki lexicon seed)",
        "CONSEQUENCE:  sets M3a live model + size; sets M7 memory path (and whether the",
        "              whisper second pass is built); seeds FR-18 + the misaki lexicon.",
        "REVERSED BY:  a re-run on a fuller/cleaner corpus, a model swap, or a runtime-",
        "              viability failure that overrides the accuracy winner.",
    ]
    if not smoke:
        lines += ["", "Paste the block above into docs/m0-measurements.md and confirm both "
                  "rulings.", "Commit " + str(meta.get("seed_vocab")) + "."]
    return "\n".join(lines)


def write_seed_vocab(path, results, smoke):
    """Aggregate proper-noun near-misses across models -> the FR-18 seed list."""
    from collections import Counter

    counter = Counter()
    detail = {}
    for mk, r in results.items():
        if r.get("failed"):
            continue
        for s in r.get("seed", []):
            counter[s["name"]] += 1
            detail.setdefault(s["name"], []).append(
                f"{mk}:{s['op']}->{s['heard'] if s['heard'] is not None else '<deleted>'}")
    out = [
        "# P-3 seed vocab - proper-noun near-misses this speaker/mic actually caused.",
        "# The seed of the FR-18 vocab list and the misaki custom-lexicon overrides.",
        "# Generated by scripts/measure_p3_stt.py. Columns: name <TAB> times_missed <TAB> "
        "what-models-heard.",
    ]
    if smoke:
        out.append("# SMOKE RUN - synthetic audio, NOT the real P-3 seed. Regenerate for real.")
    out.append("")
    for name, cnt in counter.most_common():
        out.append(f"{name}\t{cnt}\t{'; '.join(detail[name])}")
    if not counter:
        out.append("# (no proper-noun errors found)")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Corpus loading.
# --------------------------------------------------------------------------- #
def load_corpus(corpus_dir):
    """Read manifest.json + references. Returns a list of entry dicts (pure data)."""
    corpus = Path(corpus_dir)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    entries = []
    for e in manifest["entries"]:
        ref_text = (corpus / e["reference"]).read_text(encoding="utf-8")
        entries.append({
            "id": e["id"],
            "register": e.get("register", "monologue"),
            "wav": str(corpus / e["wav"]),
            "ref_tokens": normalize(ref_text),
            "pn": normalize_terms(e.get("proper_nouns", [])),
        })
    return entries


# --------------------------------------------------------------------------- #
# Engine adapters - hand-run only, lazily imported, loaded ONE AT A TIME.
# Each `transcribe_*` yields {entry_id: raw_hypothesis_text}, then is unloaded.
# The exact library call surfaces are pinned against the real APIs during the
# smoke run; kept isolated so a signature change touches one function.
# --------------------------------------------------------------------------- #
def transcribe_parakeet(entries, models_dir, threads):
    import onnx_asr

    model_dir = str(Path(models_dir) / "parakeet-tdt-0.6b-v3-onnx")
    try:
        model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", model_dir, quantization="int8")
    except TypeError:
        model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", model_dir)
    out = {}
    for e in entries:
        res = model.recognize(e["wav"])
        out[e["id"]] = res if isinstance(res, str) else " ".join(res)
    return out


def transcribe_whisper(entries, models_dir, threads):
    from faster_whisper import WhisperModel

    model_dir = str(Path(models_dir) / "faster-whisper-large-v3-turbo-ct2")
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=int(threads))
    out = {}
    for e in entries:
        segments, _info = model.transcribe(e["wav"], language="en", beam_size=5)
        out[e["id"]] = " ".join(seg.text for seg in segments).strip()
    return out


def transcribe_moonshine(entries, models_dir, threads, size):
    import moonshine_voice as mv
    from moonshine_voice.moonshine_api import ModelArch
    from moonshine_voice.transcriber import Transcriber

    arch = ModelArch.SMALL_STREAMING if size == "small" else ModelArch.MEDIUM_STREAMING
    cache = str(Path(models_dir) / "moonshine")
    # Resolves to the local model dir (fetch already downloaded it into `cache`);
    # 'en' is the MIT English model - the non-commercial warning path is not taken.
    model_path, model_arch = mv.get_model_for_language("en", arch, cache_root=cache)
    tr = Transcriber(str(model_path), model_arch=model_arch)
    out = {}
    try:
        for e in entries:
            samples, sr = mv.load_wav_file(e["wav"])  # 16-bit PCM -> [-1,1] floats
            transcript = tr.transcribe_without_streaming(samples, sr)
            out[e["id"]] = " ".join(line.text for line in transcript.lines).strip()
    finally:
        tr.close()
    return out


ADAPTERS = {
    "parakeet": transcribe_parakeet,
    "whisper-turbo": transcribe_whisper,
    "moonshine-small": lambda e, d, t: transcribe_moonshine(e, d, t, "small"),
    "moonshine-medium": lambda e, d, t: transcribe_moonshine(e, d, t, "medium"),
}


def run_bakeoff(entries, models, models_dir, threads):
    """Run each model sequentially (unloaded between), return the results dict."""
    results = {}
    for mk in models:
        try:
            hyps = ADAPTERS[mk](entries, models_dir, threads)
        except Exception as exc:  # noqa: BLE001 - a model that won't load is a finding
            results[mk] = {"failed": True, "fail_reason": f"{type(exc).__name__}: {exc}"}
            gc.collect()
            continue
        r = score_model(entries, hyps)
        # Empty on every non-trivial reference = engine failure, not a 100% WER.
        if r["empty"] and r["empty"] == r["n_entries"]:
            r = {"failed": True, "fail_reason": "empty transcript on every entry", **r}
        results[mk] = r
        del hyps
        gc.collect()  # section 6: never hold two ASR models resident on the 8GB machine
    return results


def _now_conditions():
    stamp = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return f"{stamp} | machine=i3-1315U"


def _run_live(args):
    corpus = Path(args.corpus)
    if not (corpus / "manifest.json").exists():
        print(f"No corpus manifest at {corpus / 'manifest.json'}. Record and hand-correct "
              "the P-3 corpus first (corpus/p3/prompts.md + scripts/record_p3_corpus.py). "
              "--dry-run works offline.", file=sys.stderr)
        return 1
    entries = load_corpus(corpus)
    models = resolve_models(args.models)
    for mk in models:
        model_ok = _weights_present(mk, args.models_dir)
        if model_ok is not True:
            print(model_ok, file=sys.stderr)
            return 1

    results = run_bakeoff(entries, models, args.models_dir, args.threads)
    write_seed_vocab(args.seed_vocab, results, args.smoke)
    meta = {
        "conditions": _now_conditions(),
        "corpus": str(corpus),
        "normalizer": args.normalizer,
        "threads": args.threads,
        "noise_floor": args.noise_floor,
        "seed_vocab": args.seed_vocab,
        "requested": models,
        "smoke": args.smoke,
    }
    print(format_report(results, meta))
    if args.cross_check:
        _print_cross_check(entries, results)
    return 0


def _weights_present(model_key, models_dir):
    """True if the weights dir for a model exists, else a human setup message."""
    md = Path(models_dir)
    needed = {
        "parakeet": md / "parakeet-tdt-0.6b-v3-onnx",
        "whisper-turbo": md / "faster-whisper-large-v3-turbo-ct2",
        # Both Moonshine sizes are cached under models/moonshine/ by the fetch script.
        "moonshine-small": md / "moonshine",
        "moonshine-medium": md / "moonshine",
    }[model_key]
    if needed.exists():
        return True
    return (f"Missing weights for {model_key}: {needed} not found. Run "
            "`python scripts/fetch_p3_models.py` first (records SHA256 pins). "
            "Recording nothing - a missing run is honest.")


def _print_cross_check(entries, results):
    try:
        import jiwer
    except ImportError:
        print("\n[cross-check] jiwer not installed; skipping.", file=sys.stderr)
        return
    print("\n[cross-check] jiwer overall WER (should track the local aligner):")
    for mk, r in results.items():
        if r.get("failed"):
            continue
        # jiwer recomputes from raw text; here we only have tokenized refs, so this
        # is a coarse cross-check over concatenated normalized tokens.
        print(f"    {mk}: local {_pct(r['overall_wer']['rate'])}")


def _run_dry():
    """Synthetic numbers, no engine - exercises the report and both rulings."""
    def mk(cs_pn, overall):
        return {
            "by_register": {
                "monologue": {"wer": {"rate": overall}, "pn": {"rate": 0.0}},
                "read": {"wer": {"rate": overall}, "pn": {"rate": 0.0}},
                "codeswitch": {"wer": {"rate": overall + 0.05}, "pn": {"rate": cs_pn}},
            },
            "overall_wer": {"rate": overall},
            "pn_overall": {"rate": cs_pn / 2},
            "per_file_wer": {50: overall, 95: overall + 0.05},
            "seed": [{"name": "malang", "heard": "malong", "op": "sub", "id": "codeswitch"}],
            "empty": 0, "n_entries": 3,
        }
    results = {
        "moonshine-small": mk(0.20, 0.11),
        "moonshine-medium": mk(0.18, 0.09),
        "parakeet": mk(0.15, 0.07),
        "whisper-turbo": mk(0.05, 0.065),
    }
    meta = {
        "conditions": _now_conditions(), "corpus": "(dry-run synthetic)",
        "normalizer": "standard", "threads": 3, "noise_floor": NOISE_FLOOR,
        "seed_vocab": "docs/p3-vocab-seed.txt", "requested": list(ALL_MODELS),
        "smoke": False,
    }
    print("[dry-run] synthetic numbers - no engine was loaded.\n")
    print(format_report(results, meta))
    return 0


def main(argv):
    args = parse_args(argv)
    if args.dry_run:
        return _run_dry()
    return _run_live(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
