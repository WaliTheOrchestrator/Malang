#!/usr/bin/env python3
"""P-2 measurement gate: Kokoro-82M real-time factor (RTF) on the actual laptop.

Spec: .claude/specs/p-2-kokoro-rtf-measurement.md (malang-phase1-spec.md section 9).

This is a HAND-RUN measurement script, not a test. It synthesizes a fixed corpus
of 10 varied-length sentences with Kokoro-82M and measures RTF - the ratio of
synthesis wall-time to the duration of audio produced. RTF is the number that
decides whether Kokoro can be Malang's voice on this CPU, or whether the
pre-decided fallback ladder (quantized ONNX -> Supertonic 3 -> Piper) opens.

    python scripts/measure_p2_kokoro.py --label mains
    python scripts/measure_p2_kokoro.py --label battery
    python scripts/measure_p2_kokoro.py --dry-run     # offline; exercises the report

Gate (spec section 9): aggregate p50 RTF < 0.8 sustained -> Kokoro confirmed.

Honesty rules this script keeps (spec section 12):
  - RTF = synthesis_wall_time / (n_samples / sample_rate); the sample rate is READ
    from the engine's return value, never hardcoded.
  - Model load and a pre-warm dummy synthesis are EXCLUDED from timing (a cold
    first call is not the production number).
  - "Sustained" means the corpus is synthesized over many rounds; round-1-vs-round-N
    drift is reported as the thermal early-warning (this U-series chassis throttles).
  - The corpus is fixed and byte-identical across rounds and power labels, so
    mains-vs-battery and round-1-vs-round-N are comparable.
  - A non-silence guard fires on the first synthesis: the espeak-ng path in this
    package family has returned empty audio with no exception on Windows, and RTF
    over silence is a meaningless number that looks like a pass.

RTF is NOT the section 5 "300ms first-audio" budget - that is first-micro-chunk
latency (HP16), measured at M3a with the real micro-chunk pipeline, not here.

The `kokoro_onnx` import is deliberately lazy (inside the engine layer) so the pure
core, --dry-run, and the unit tests need nothing installed. This script is P-2
self-contained: it does NOT import from P-1's probe (that branch is unmerged).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import inspect
import math
import sys
import time

# The gate threshold (spec section 9), read on the aggregate p50 RTF.
GATE_RTF = 0.8
# Round-N drift above this fraction is a thermal-throttle finding (spec section 12).
DRIFT_WARN = 0.15
# A synthesis whose peak |sample| is below this is treated as silence (guard, rule 2).
SILENCE_FLOOR = 0.01

# The fixed corpus: 10 sentences spanning short (<=5 words), medium, and long
# (>25 words). One line carries "Malang" and a family name for realism - graded
# for SPEED only; pronunciation correctness is P-4/P-6. HP16: short strings carry
# per-call overhead and score WORSE RTF than long ones, so the spread is the point.
CORPUS = [
    # --- short (<=5 words) ---
    "Yes, of course.",
    "What time is it?",
    "Tell me one thing.",
    # --- medium (6-25 words) ---
    "The moon is unusually bright over the valley tonight.",
    "I have been turning that zoning question over since this morning.",
    "Malang, remind me what my cousin Zarak said about the loan.",
    "Let us walk through the plan one careful step at a time.",
    # --- long (>25 words) ---
    "When you first described the project to me I thought it was too large to "
    "finish, but the more we broke it into small shippable pieces the more it "
    "started to look like something you could actually carry to the end.",
    "The thing I keep coming back to is that the record outlasts the rented mind, "
    "and every conversation we hold now is quietly building the one archive that "
    "no change of model can ever take away from you.",
    "There is a particular kind of quiet that arrives late at night when the house "
    "has gone still, and in that quiet the questions you avoided all day finally "
    "come and sit down beside you and ask to be answered honestly.",
]


# --------------------------------------------------------------------------- #
# Pure core - no engine, unit-tested. (Self-contained: no import from P-1.)
# --------------------------------------------------------------------------- #
def percentiles(values, ps):
    """Nearest-rank percentiles. `ps` is an iterable of percentiles in [0, 100].

    Returns {p: value}. For an empty input every percentile maps to None - a
    missing measurement is honest; a zero would be a lie (working-style rule).
    """
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


def length_band(text):
    """Classify a sentence by word count: short (<=5) / medium / long (>25)."""
    words = len(text.split())
    if words <= 5:
        return "short"
    if words > 25:
        return "long"
    return "medium"


def compute_rtf(wall_s, n_samples, sample_rate):
    """RTF = synthesis wall-time / audio duration. None if there is no audio.

    audio_duration = n_samples / sample_rate. A None here (zero-length audio)
    is the silent-synthesis case the guard catches - never report it as a number.
    """
    if not n_samples or not sample_rate:
        return None
    audio_s = n_samples / sample_rate
    if audio_s <= 0:
        return None
    return wall_s / audio_s


def is_silent(peak_abs, floor=SILENCE_FLOOR):
    """True if the loudest sample is below the silence floor (rule 2 guard)."""
    return peak_abs is None or peak_abs < floor


def _gate_ruling(rtf_p50):
    """The pre-decided gate branch (spec section 9) for an aggregate p50 RTF."""
    if rtf_p50 is None:
        return "no RTF recorded - synthesis produced no measurable audio"
    if rtf_p50 < GATE_RTF:
        return (f"Kokoro CONFIRMED (aggregate p50 RTF {rtf_p50:.3f} < 0.8 sustained) "
                "- this build stays the voice")
    return (f"gate FAILS for this build (aggregate p50 RTF {rtf_p50:.3f} >= 0.8) - open "
            "the fallback ladder: quantized ONNX (spec section 9) -> Supertonic 3 -> "
            "Piper (design section 2/4, D-4)")


def _drift_note(first, last):
    """Round-1 vs round-N drift as a percentage, with a thermal-throttle flag."""
    if first is None or last is None or first <= 0:
        return "n/a"
    frac = (last - first) / first
    flag = "  <-- THERMAL DRIFT >15%, see spec section 12" if frac > DRIFT_WARN else ""
    return f"round1 p50 {first:.3f} -> roundN p50 {last:.3f} ({frac:+.1%}){flag}"


def format_ruling_block(label, conditions, agg, by_band, drift, meta):
    """Emit the /measure skill's ruling shape, ready to paste into docs/."""
    def fmt(d, key):
        v = d.get(key)
        return "n/a" if v is None else f"{v:.3f}"

    agg_p50 = agg.get(50)
    band_line = "  ".join(
        f"{b} p50 {fmt(by_band.get(b, {}), 50)} p95 {fmt(by_band.get(b, {}), 95)}"
        for b in ("short", "medium", "long")
    )
    lines = [
        "GATE: P-2",
        f"DATE / CONDITIONS: {conditions}" + (f" | label={label}" if label else ""),
        f"    engine: {meta.get('engine', 'n/a')} | build={meta.get('build')} | "
        f"voice={meta.get('voice')} | trim={meta.get('trim')} | "
        f"rounds={meta.get('rounds')} | threads={meta.get('threads')}",
        f"    core-class: {meta.get('core_class', 'not captured (P-5 mechanism)')}",
        f"    non-silence guard: {meta.get('silence', 'n/a')}",
        "RAW NUMBERS:",
        f"    RTF aggregate  p50 {fmt(agg, 50)}  p95 {fmt(agg, 95)}  "
        f"(n={meta.get('n', 0)} syntheses)",
        f"    by length:     {band_line}",
        f"    drift:         {drift}",
        f"    elapsed:       {meta.get('elapsed', 'n/a')}  "
        "(judge whether the run reached the minute-3-10 throttle window)",
        f"RULING:            {_gate_ruling(agg_p50)}",
        "CONSEQUENCE:       spec section 5 active-session 'fan behavior acceptable' + the "
        "TTS stage. RTF FEEDS but does NOT equal the 300ms first-audio budget (HP16) - "
        "that is first-micro-chunk latency, measured at M3a.",
        "REVERSED BY:       a later re-run crossing 0.8 the other way - a quantized/fp16 "
        "build, a cooler/hotter thermal state, a model swap, or the battery run.",
    ]
    return "\n".join(lines)


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="measure_p2_kokoro.py",
        description="P-2: measure Kokoro-82M sustained RTF on this laptop.",
    )
    p.add_argument("--rounds", type=int, default=5,
                   help="Times the fixed corpus is synthesized (default: %(default)s). "
                        "'Sustained' is many rounds, not one warm call.")
    p.add_argument("--voice", default="af_heart",
                   help="Kokoro voice id (default: %(default)s). Identity is P-6's "
                        "call, not P-2's; RTF is ~voice-independent.")
    p.add_argument("--threads", type=int, default=3,
                   help="Requested ORT intra_op threads (default: %(default)s). Applied "
                        "only if the engine exposes it; otherwise engine default, recorded.")
    p.add_argument("--build", choices=("standard", "quantized"), default="standard",
                   help="standard -> kokoro-v1.0.onnx; quantized -> kokoro-v1.0.int8.onnx "
                        "(the first fallback rung). Default: %(default)s.")
    p.add_argument("--model-path", default="",
                   help="Path to the .onnx model. Default derived from --build under models/.")
    p.add_argument("--voices-path", default="models/voices-v1.0.bin",
                   help="Path to the voices .bin (default: %(default)s).")
    p.add_argument("--trim", dest="trim", action="store_true", default=True,
                   help="Trim leading/trailing silence (engine default; recorded).")
    p.add_argument("--no-trim", dest="trim", action="store_false",
                   help="Do not trim - keeps the full synthesized duration in the RTF denominator.")
    p.add_argument("--silence-floor", type=float, default=SILENCE_FLOOR, dest="silence_floor",
                   help="Peak |sample| below this on the first call = silent synthesis, "
                        "fail loudly (default: %(default)s).")
    p.add_argument("--label", default="",
                   help="REQUIRED framing for a real run: mains or battery. A run with no "
                        "power label is not a valid P-2 record (spec section 4 P-4).")
    p.add_argument("--dry-run", action="store_true",
                   help="Offline: exercise the report on synthetic numbers, no engine.")
    return p.parse_args(argv)


def _model_path(args):
    if args.model_path:
        return args.model_path
    name = "kokoro-v1.0.int8.onnx" if args.build == "quantized" else "kokoro-v1.0.onnx"
    return f"models/{name}"


def _now_conditions():
    stamp = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    return f"{stamp} | power=[confirm: mains/battery] | machine=i3-1315U"


def _aggregate(samples_by_band, rtf_by_round):
    """Turn raw per-synthesis RTFs into the aggregate + per-band + drift views."""
    all_rtfs = [r for band in samples_by_band.values() for r in band]
    agg = percentiles(all_rtfs, (50, 95))
    by_band = {b: percentiles(v, (50, 95)) for b, v in samples_by_band.items()}
    first = percentiles(rtf_by_round.get(1, []), (50,)).get(50)
    last_round = max(rtf_by_round) if rtf_by_round else None
    last = percentiles(rtf_by_round.get(last_round, []), (50,)).get(50) if last_round else None
    return agg, by_band, _drift_note(first, last), len(all_rtfs)


def run_corpus(synth, rounds, silence_floor):
    """Synthesize the fixed corpus `rounds` times via `synth(text) -> (wall, n, sr, peak)`.

    Returns (samples_by_band, rtf_by_round, elapsed_s, error). `error` is None on a
    clean run, or a message string if ANY synthesis came back silent or empty - in
    which case the run ABORTS immediately. This is rule 2 extended across the whole
    run, not just the warm-up call: one silent synthesis (the espeak-ng degrade this
    project is built to catch) makes every RTF after it untrustworthy, and a
    silent-but-full-length clip would otherwise compute a normal-looking RTF that
    passes. The peak amplitude is checked on every item, never computed and discarded.
    """
    samples_by_band = {"short": [], "medium": [], "long": []}
    rtf_by_round = {}
    t0 = time.perf_counter()
    for rnd in range(1, max(1, rounds) + 1):
        rtf_by_round[rnd] = []
        for text in CORPUS:
            wall, n, sr, peak = synth(text)
            if is_silent(peak, silence_floor) or not n:
                return samples_by_band, rtf_by_round, time.perf_counter() - t0, (
                    f"SILENT SYNTHESIS mid-run (round {rnd}, {text[:40]!r}...): peak "
                    f"{peak:.5f} < floor {silence_floor}. espeak-ng likely failed "
                    "silently; the run is untrustworthy. Recording nothing.")
            rtf = compute_rtf(wall, n, sr)
            if rtf is None:
                return samples_by_band, rtf_by_round, time.perf_counter() - t0, (
                    f"ZERO-DURATION synthesis mid-run (round {rnd}, {text[:40]!r}...). "
                    "Recording nothing.")
            samples_by_band[length_band(text)].append(rtf)
            rtf_by_round[rnd].append(rtf)
    return samples_by_band, rtf_by_round, time.perf_counter() - t0, None


def _core_note():
    """Best-effort, honest core note. True P/E-class resolution is P-5's mechanism."""
    try:
        import os
        if hasattr(os, "sched_getaffinity"):
            return (f"{len(os.sched_getaffinity(0))} cpus in affinity mask "
                    "(P/E class not resolved - P-5 mechanism)")
    except Exception:  # noqa: BLE001
        pass
    return "not captured (P-5 mechanism)"


# --------------------------------------------------------------------------- #
# Engine layer - hand-run only, lazily imports kokoro_onnx.
# --------------------------------------------------------------------------- #
def make_kokoro(model_path, voices_path, threads):
    """Construct a Kokoro engine, pinning ORT threads iff the API exposes it.

    Returns (engine, description). kokoro-onnx's confirmed constructor is
    Kokoro(model_path, voices_path); some versions add Kokoro.from_session(...),
    which is the only honest way to set intra_op threads. If neither path takes
    a thread count, we record 'engine default threading' rather than pretend.
    """
    import onnxruntime as ort  # noqa: F401  (pulled in by kokoro-onnx)
    import kokoro_onnx

    if threads and hasattr(kokoro_onnx.Kokoro, "from_session"):
        try:
            so = ort.SessionOptions()
            so.intra_op_num_threads = int(threads)
            so.inter_op_num_threads = 1
            sess = ort.InferenceSession(
                model_path, sess_options=so, providers=["CPUExecutionProvider"]
            )
            return (kokoro_onnx.Kokoro.from_session(sess, voices_path),
                    f"kokoro-onnx via from_session (intra_op={threads})")
        except Exception:  # noqa: BLE001 - fall back honestly, do not fake control
            pass
    return (kokoro_onnx.Kokoro(model_path, voices_path),
            "kokoro-onnx default threading (thread count not enforced)")


def synthesize(engine, text, voice, trim):
    """One synthesis. Returns (wall_seconds, n_samples, sample_rate, peak_abs)."""
    call = engine.create
    kwargs = {}
    if "trim" in inspect.signature(call).parameters:
        kwargs["trim"] = trim
    t0 = time.perf_counter()
    samples, sample_rate = call(text, voice=voice, **kwargs)
    wall = time.perf_counter() - t0
    n = int(getattr(samples, "shape", [len(samples)])[0])
    peak = float(abs(samples).max()) if n else 0.0
    return wall, n, int(sample_rate), peak


def _run_live(args):
    import os

    # Spec section 7/13: a run with no power label is not a valid P-2 record. Refuse
    # BEFORE spending minutes synthesizing, so an unlabelled block can never be pasted
    # as if it were a real ruling (both reviewers flagged the old soft warning).
    if not args.label:
        print("Refusing to run: --label is REQUIRED on a live run (mains or battery). "
              "A P-2 record without a power source is not valid (spec section 4 P-4 / "
              "section 7). Re-run with --label mains, then --label battery.",
              file=sys.stderr)
        return 2

    model_path = _model_path(args)
    voices_path = args.voices_path
    for path, what in ((model_path, "model"), (voices_path, "voices")):
        if not os.path.exists(path):
            print(
                f"Missing {what} file: {path}\n"
                "Download the model-files-v1.0 release assets (kokoro-v1.0.onnx / "
                "kokoro-v1.0.int8.onnx + voices-v1.0.bin) from "
                "https://github.com/thewh1teagle/kokoro-onnx/releases and place them "
                "under models/. Recording nothing - a missing run is honest.",
                file=sys.stderr,
            )
            return 1

    try:
        engine, engine_desc = make_kokoro(model_path, voices_path, args.threads)
    except ImportError as exc:
        print(f"kokoro-onnx is not installed ({exc}). `uv add kokoro-onnx` in a "
              "3.12 venv (NOT the system 3.14). --dry-run works offline.",
              file=sys.stderr)
        return 2

    trim_supported = "trim" in inspect.signature(engine.create).parameters

    # Pre-warm (D-10): one dummy synthesis, EXCLUDED from timing. It also arms the
    # non-silence guard before any RTF is trusted (rule 2).
    _, warm_n, _, warm_peak = synthesize(engine, "Warming up.", args.voice, args.trim)
    if is_silent(warm_peak, args.silence_floor) or not warm_n:
        print(
            f"SILENT SYNTHESIS on warm-up: peak |sample| {warm_peak:.5f} < floor "
            f"{args.silence_floor}. The espeak-ng path likely failed silently (no "
            "exception). RTF over silence would be a meaningless pass - refusing to "
            "measure. Recording nothing.",
            file=sys.stderr,
        )
        return 1

    # The measured loop silence-checks EVERY synthesis (not just the warm-up) and
    # aborts loudly on the first silent/empty clip - the latency-auditor BLOCKING fix.
    samples_by_band, rtf_by_round, elapsed, error = run_corpus(
        lambda text: synthesize(engine, text, args.voice, args.trim),
        args.rounds, args.silence_floor,
    )
    if error:
        print(error, file=sys.stderr)
        return 1

    agg, by_band, drift, n_total = _aggregate(samples_by_band, rtf_by_round)
    meta = {
        "engine": engine_desc, "build": args.build, "voice": args.voice,
        "trim": f"{args.trim} (applied={trim_supported})", "rounds": args.rounds,
        "threads": args.threads, "n": n_total, "core_class": _core_note(),
        "elapsed": f"{elapsed:.1f}s total over {args.rounds} rounds",
        "silence": f"passed (warm peak {warm_peak:.3f}; floor {args.silence_floor})",
    }
    print(format_ruling_block(args.label, _now_conditions(), agg, by_band, drift, meta))
    print(
        "\nPaste the block above into docs/m0-measurements.md and confirm the RULING. "
        "Run again on the OTHER power source (--label mains AND --label battery)."
    )
    return 0


def _run_dry():
    """Synthetic numbers, no engine - exercises the report and the ruling."""
    samples_by_band = {
        "short": [0.62, 0.65, 0.68, 0.60, 0.66],
        "medium": [0.52, 0.55, 0.50, 0.53, 0.51],
        "long": [0.44, 0.46, 0.43, 0.45, 0.44],
    }
    rtf_by_round = {1: [0.60, 0.51, 0.43], 5: [0.68, 0.55, 0.46]}
    agg, by_band, drift, n_total = _aggregate(samples_by_band, rtf_by_round)
    meta = {
        "engine": "synthetic (dry-run) - no engine loaded", "build": "standard",
        "voice": "af_heart", "trim": "True (applied=n/a)", "rounds": 5, "threads": 3,
        "n": n_total, "core_class": "not captured (dry-run)",
        "elapsed": "n/a (dry-run)", "silence": "n/a (dry-run)",
    }
    print("[dry-run] synthetic numbers - no engine was loaded.\n")
    print(format_ruling_block("", _now_conditions(), agg, by_band, drift, meta))
    return 0


def main(argv):
    args = parse_args(argv)
    if args.dry_run:
        return _run_dry()
    return _run_live(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
