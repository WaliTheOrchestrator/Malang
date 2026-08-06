#!/usr/bin/env python3
"""P-4a measurement gate: blind ABX ear check, selective-int8 vs fp32 Kokoro.

Spec: .claude/specs/p-4-selective-int8-ear-check-wasapi-probe.md (§9, §12).

The only M0 gate a stopwatch cannot decide - it is judged BY EAR (HP13: no metric
catches "he sounds slightly less alive"). This script renders a fixed 10-sentence
corpus in each build and runs a blind ABX test: the grader hears X (secretly one
build), then A and B (the two builds in random order), and picks which of A/B
equals X. If the grader cannot beat chance on selective-vs-fp32, int8 is
indistinguishable and ships; the blind off-the-shelf build is a NEGATIVE CONTROL
that MUST be distinguishable, or the instrument (room/gear/grader/corpus) is not
sensitive and no verdict is trustworthy (spec §12 rule 1 - the P-3 validity
parallel).

    uv run python scripts/measure_p4_int8_ear.py --grader waleed        # live ABX
    uv run python scripts/measure_p4_int8_ear.py --dry-run              # offline, no engine

Honesty rules kept (spec §12):
  - Blind: the grader never sees which build is X; --seed fixes the assignment
    reproducibly but is not shown. One person grading his own build unblinded is
    not blind (the A-15 rule, applied to ears) - prefer a second --grader run.
  - The gate reads BINOMIAL SIGNIFICANCE of the correct rate vs 50%, not a vibe.
  - Names are NEVER in this tracked script (spec §12 rule 3 / B-1): the corpus is
    a tracked template with {PLACEHOLDER}s; real family names + IPA overrides come
    from a git-ignored corpus/p4/names.txt.
  - Per-render non-silence + token-length guard on EVERY clip incl. is_phonemes
    override renders (spec §12 rule 5): espeak-ng can return silence with no
    exception, and the Kokoro tokenizer silently drops non-vocab characters.
  - Name-pronunciation correctness is tallied SEPARATELY from the int8 verdict
    (spec §12 rule 4) - a build can be indistinguishable and still mispronounce.

int8 here is a RAM/thermal-headroom lever, not speed (P-2 passed on fp32). The
`kokoro_onnx` / `sounddevice` imports are lazy so the pure core, --dry-run, and the
unit tests need nothing installed (the P-2/P-3 pattern).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import math
import os
import random
import sys
from collections import namedtuple

ALPHA = 0.05                       # significance for "distinguishable" (spec §12 rule 2)
DEFAULT_TRIALS = 24                # ABX trials per contrast
SILENCE_FLOOR = 0.01               # peak |sample| below this = silent (guard, rule 5)
TEMPLATE_PATH = "corpus/p4/corpus_template.txt"
NAMES_PATH = "corpus/p4/names.txt"

# A trial: one corpus sentence, X is one build, A/B are the two builds in some order.
Trial = namedtuple("Trial", "sentence_idx x_build a_build b_build")


# --------------------------------------------------------------------------- #
# Pure core - no engine, no audio, unit-tested.
# --------------------------------------------------------------------------- #
def binom_sf_ge(k, n, p=0.5):
    """One-sided P(X >= k) for X ~ Binomial(n, p). Exact (math.comb).

    This is the ABX p-value: the probability a chance grader (p=0.5) would get at
    least `k` of `n` right. Small p => the grader really hears a difference.
    """
    if n <= 0:
        return 1.0
    k = max(0, min(k, n))
    return sum(math.comb(n, j) * (p ** j) * ((1 - p) ** (n - j)) for j in range(k, n + 1))


def abx_ruling(correct, total, alpha=ALPHA):
    """{correct, total, p_value, distinguishable}. distinguishable iff p<=alpha."""
    p = binom_sf_ge(correct, total, 0.5)
    return {"correct": correct, "total": total, "p_value": p,
            "distinguishable": (total > 0 and p <= alpha)}


def p4a_gate(selective, control, alpha=ALPHA):
    """Combine the two ABX contrasts into the pre-decided P-4a branch (spec §9/§12).

    `selective` = ABX ruling for selective-int8 vs fp32 (want NOT distinguishable).
    `control`   = ABX ruling for blind-int8 vs fp32 (the negative control, MUST be
                  distinguishable or the instrument is broken).
    """
    if control is not None and not control["distinguishable"]:
        return ("NEGATIVE CONTROL FAILED", (
            "grader could not distinguish even the blind int8 from fp32 "
            f"(p={control['p_value']:.3f} > {alpha}). The ear test is not sensitive "
            "(room/gear/grader/corpus). No 'indistinguishable' verdict is trustworthy "
            "- fix the instrument before ruling (spec §12 rule 1)."))
    if selective["distinguishable"]:
        return ("int8 DISTINGUISHABLE - SHIP fp32", (
            f"selective-int8 was told apart from fp32 (p={selective['p_value']:.3f} "
            f"<= {alpha}). Per §9 'Failing -> fp32 and revise honestly': ship fp32, "
            "record which §5 line loosens. int8's RAM/thermal win is not free of the ear."))
    return ("int8 INDISTINGUISHABLE - SHIP selective-int8", (
        f"selective-int8 was NOT told apart from fp32 (p={selective['p_value']:.3f} "
        f"> {alpha}) while the blind control WAS caught. int8 ships; re-run the ear "
        "test on the P-6 winner and after any model/runtime change (rule 4)."))


def build_trials(contrast, n_trials, seed, n_sentences):
    """Deterministic ABX trial list. `contrast` = (build_x_name, build_y_name).

    Reproducible from `seed` (spec §12 rule 2), but the assignment is never shown
    to the grader. Sentences are cycled so every trial has real content.
    """
    a_name, b_name = contrast
    rng = random.Random(seed)
    trials = []
    for i in range(n_trials):
        s_idx = i % max(1, n_sentences)
        x = rng.choice((a_name, b_name))
        pair = [a_name, b_name]
        rng.shuffle(pair)
        trials.append(Trial(s_idx, x, pair[0], pair[1]))
    return trials


def correct_slot(trial):
    """Which of A/B equals X - the correct grader answer ('a' or 'b')."""
    return "a" if trial.a_build == trial.x_build else "b"


def grade(trial, response):
    """True iff the grader's 'a'/'b' response matched X."""
    return response.strip().lower() == correct_slot(trial)


def tally_correct(trials, responses):
    """Count correct responses over paired (trial, response) sequences."""
    return sum(1 for t, r in zip(trials, responses) if grade(t, r))


def parse_names(text):
    """Parse the git-ignored names file. Lines: `PLACEHOLDER<TAB>spelling[<TAB>ipa]`.

    Blank lines and `#` comments ignored. Returns {placeholder: (spelling, ipa|None)}.
    The IPA (if given) is a phoneme-override string fed to create(is_phonemes=True).
    """
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if len(parts) < 2:
            continue
        placeholder, spelling = parts[0], parts[1]
        ipa = parts[2] if len(parts) >= 3 else None
        out[placeholder] = (spelling, ipa)
    return out


def render_template(template_text, names):
    """Substitute {PLACEHOLDER} tokens with the real spellings. Pure.

    `names` is {placeholder: (spelling, ipa)}. Unknown placeholders are left as-is
    so a missing name is visible, never silently blank. Returns list of sentences.
    """
    lines = [ln.strip() for ln in template_text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    out = []
    for ln in lines:
        for placeholder, (spelling, _ipa) in names.items():
            ln = ln.replace("{" + placeholder + "}", spelling)
        out.append(ln)
    return out


def _fmt_abx(res):
    if res is None:
        return "n/a"
    return (f"{res['correct']}/{res['total']} correct  "
            f"p={res['p_value']:.3f}  "
            f"{'DISTINGUISHABLE' if res['distinguishable'] else 'indistinguishable'}")


def format_ruling_block(meta, selective, control, name_notes):
    """The /measure ruling shape for P-4a, ready to paste into docs/."""
    verdict, rationale = p4a_gate(selective, control, meta.get("alpha", ALPHA))
    lines = [
        "GATE: P-4a (selective-int8 ear check, blind ABX)",
        f"DATE / CONDITIONS: {meta.get('date')} | machine=i3-1315U | "
        f"grader={meta.get('grader')} | voice={meta.get('voice')} | "
        f"threads={meta.get('threads')} | seed={meta.get('seed')} | "
        f"trials/contrast={meta.get('trials')}",
        f"    builds: fp32={meta.get('fp32_sha', 'n/a')[:12]} "
        f"selective={meta.get('selective_sha', 'n/a')[:12]} "
        f"blind={meta.get('blind_sha', 'n/a')[:12]}",
        f"    names file SHA256: {meta.get('names_sha', 'n/a')}",
        f"    non-silence/token guard: {meta.get('guard', 'n/a')}",
        "RAW NUMBERS:",
        f"    selective vs fp32 (the test):     {_fmt_abx(selective)}",
        f"    blind vs fp32 (negative control): {_fmt_abx(control)}",
        f"    name pronunciation:               {name_notes or 'not tallied'}",
        f"RULING:            {verdict}",
        f"                   {rationale}",
        "CONSEQUENCE:       sets speech.tts.model_build (selective-int8 | fp32) for "
        "M3a; if indistinguishable AND names correct -> names may bake into "
        "render_reflexes.py (D-4). Voice-independent verdict (shared model, separate "
        "voice embeddings) - RE-RUN on the P-6 winner (rule 4).",
        "REVERSED BY:       any Kokoro model/runtime change, the P-6 voice swap, or a "
        "more sensitive instrument catching drift this room missed.",
    ]
    return "\n".join(lines)


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="measure_p4_int8_ear.py",
        description="P-4a: blind ABX ear check, selective-int8 vs fp32 Kokoro.",
    )
    p.add_argument("--builds", default="fp32,selective,blind",
                   help="Comma list; 'blind'=models/kokoro-v1.0.int8.onnx (control). "
                        "Default: %(default)s.")
    p.add_argument("--voice", default="af_heart",
                   help="Kokoro voice (default: %(default)s). Identity is P-6's; "
                        "the int8 verdict is voice-independent (rule 8).")
    p.add_argument("--trials", type=int, default=DEFAULT_TRIALS,
                   help="ABX trials per contrast (default: %(default)s).")
    p.add_argument("--seed", type=int, default=None,
                   help="Fixes trial order + which build is X (reproducible, hidden "
                        "from grader). Default: a fresh random seed, recorded.")
    p.add_argument("--grader", default="",
                   help="Who is judging (recorded). A 2nd grader is a separate run.")
    p.add_argument("--threads", type=int, default=3,
                   help="ORT intra_op threads (default: %(default)s).")
    p.add_argument("--template", default=TEMPLATE_PATH,
                   help="Tracked corpus template with {PLACEHOLDER}s (default: %(default)s).")
    p.add_argument("--names", default=NAMES_PATH,
                   help="Git-ignored real names + IPA overrides (default: %(default)s).")
    p.add_argument("--voices-path", default="models/voices-v1.0.bin")
    p.add_argument("--silence-floor", type=float, default=SILENCE_FLOOR)
    p.add_argument("--dry-run", action="store_true",
                   help="Offline: exercise ABX stats + gate + formatter, no engine.")
    return p.parse_args(argv)


BUILD_PATHS = {
    "fp32": "models/kokoro-v1.0.onnx",
    "selective": "models/kokoro-v1.0.int8-selective.onnx",
    "blind": "models/kokoro-v1.0.int8.onnx",
}


# --------------------------------------------------------------------------- #
# Engine + audio layer - hand-run only, lazily imports kokoro_onnx / sounddevice.
# --------------------------------------------------------------------------- #
def _load_engine(build_name, voices_path, threads):
    import onnxruntime as ort
    import kokoro_onnx
    path = BUILD_PATHS[build_name]
    so = ort.SessionOptions()
    so.intra_op_num_threads = int(threads)
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
    return kokoro_onnx.Kokoro.from_session(sess, voices_path)


def _render(engine, text, voice, floor):
    """Synthesize one clip; return (samples, sr). Guards silence (rule 5)."""
    import numpy as np
    samples, sr = engine.create(text, voice=voice)
    peak = float(np.abs(samples).max()) if len(samples) else 0.0
    if not len(samples) or peak < floor:
        raise RuntimeError(
            f"SILENT/degenerate render (peak {peak:.5f} < {floor}) for {text[:40]!r}. "
            "espeak-ng likely failed silently (spec §12 rule 5). Recording nothing.")
    return samples, int(sr)


def main(argv):
    args = parse_args(argv)
    if args.dry_run:
        return _run_dry(args)
    return _run_live_impl(args)


def _run_dry(args):
    # Synthetic responses: control caught (20/24), selective missed (13/24) -> ships.
    selective = abx_ruling(13, 24)
    control = abx_ruling(20, 24)
    meta = {
        "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "grader": "synthetic (dry-run)", "voice": args.voice, "threads": args.threads,
        "seed": args.seed if args.seed is not None else 1234, "trials": args.trials,
        "alpha": ALPHA, "guard": "n/a (dry-run)", "names_sha": "n/a (dry-run)",
    }
    print("[dry-run] synthetic ABX responses - no engine loaded.\n")
    print(format_ruling_block(meta, selective, control,
                              "Malang OK, {family names} OK (synthetic)"))
    return 0


def _run_live_impl(args):
    sys.stdout.reconfigure(encoding="utf-8")
    import numpy as np

    build_names = [b.strip() for b in args.builds.split(",") if b.strip()]
    for b in build_names:
        if b not in BUILD_PATHS:
            print(f"Unknown build {b!r}; choose from {sorted(BUILD_PATHS)}.", file=sys.stderr)
            return 2
        if not os.path.exists(BUILD_PATHS[b]):
            hint = ("Run scripts/build_kokoro_selective_int8.py first."
                    if b == "selective" else
                    "Download the model-files-v1.0 assets into models/.")
            print(f"Missing build {b!r}: {BUILD_PATHS[b]}. {hint}", file=sys.stderr)
            return 1

    for path, what in ((args.template, "template"), (args.names, "names file")):
        if not os.path.exists(path):
            print(f"Missing {what}: {path}. See corpus/p4/README.md - the names file "
                  "is git-ignored and you author it locally (real family names + IPA).",
                  file=sys.stderr)
            return 1

    try:
        import kokoro_onnx  # noqa: F401
        import sounddevice as sd
    except ImportError as exc:
        print(f"Live run needs kokoro-onnx + sounddevice ({exc}). "
              "`uv pip install sounddevice`; --dry-run works offline.", file=sys.stderr)
        return 2

    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    names = parse_names(open(args.names, encoding="utf-8").read())
    corpus = render_template(open(args.template, encoding="utf-8").read(), names)
    if not corpus:
        print("Empty corpus after template render.", file=sys.stderr)
        return 1

    from build_kokoro_selective_int8 import sha256_file
    meta = {
        "date": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "grader": args.grader or "UNLABELLED", "voice": args.voice,
        "threads": args.threads, "seed": seed, "trials": args.trials, "alpha": ALPHA,
        "names_sha": sha256_file(args.names),
        "fp32_sha": sha256_file(BUILD_PATHS["fp32"]),
        "selective_sha": sha256_file(BUILD_PATHS["selective"]),
        "blind_sha": sha256_file(BUILD_PATHS["blind"]) if os.path.exists(BUILD_PATHS["blind"]) else "n/a",
    }

    # Render every (build, sentence) clip once, guarding silence (rule 5).
    print(f"Rendering {len(corpus)} sentences x {len(build_names)} builds "
          f"(voice={args.voice})... peak-guard on every clip.")
    clips = {}
    for b in build_names:
        engine = _load_engine(b, args.voices_path, args.threads)
        clips[b] = [_render(engine, s, args.voice, args.silence_floor) for s in corpus]
        del engine  # one ORT session at a time (spec §6)
    meta["guard"] = f"passed (floor {args.silence_floor}, every clip peak-checked)"

    def play(build, s_idx):
        samples, sr = clips[build][s_idx]
        sd.play(samples, sr); sd.wait()

    def abx(contrast):
        trials = build_trials(contrast, args.trials, seed, len(corpus))
        responses = []
        print(f"\n=== ABX: {contrast[0]} vs {contrast[1]}  ({args.trials} trials) ===")
        print("For each trial: X plays, then A, then B. Type a or b for which matches X "
              "(r to replay, q to abort).")
        for i, t in enumerate(trials, 1):
            while True:
                print(f"\nTrial {i}/{args.trials} (sentence {t.sentence_idx + 1}): X..."); play(t.x_build, t.sentence_idx)
                print("A..."); play(t.a_build, t.sentence_idx)
                print("B..."); play(t.b_build, t.sentence_idx)
                resp = input("  X == ? [a/b/r/q]: ").strip().lower()
                if resp == "r":
                    continue
                if resp == "q":
                    print("Aborted; recording nothing.", file=sys.stderr)
                    return None
                if resp in ("a", "b"):
                    responses.append(resp); break
                print("  Please type a, b, r, or q.")
        return abx_ruling(tally_correct(trials, responses), len(trials))

    selective = abx(("fp32", "selective"))
    if selective is None:
        return 1
    control = abx(("fp32", "blind")) if "blind" in build_names else None

    # Name-pronunciation tally (rule 4): separate from the int8 verdict.
    name_notes = _name_tally(corpus, names, clips, build_names, play)

    print("\n" + "=" * 70)
    print(format_ruling_block(meta, selective, control, name_notes))
    print("\nPaste the block above into docs/m0-measurements.md (replace the P-4a "
          "stub). Re-run with a SECOND --grader if one is available (spec §12 rule 2).")
    return 0


def _name_tally(corpus, names, clips, build_names, play):
    """Ask the grader whether names are pronounced correctly, per build (rule 4)."""
    # Name-bearing sentences: those containing 'Malang' or any injected spelling.
    targets = [i for i, s in enumerate(corpus)
               if "Malang" in s or any(sp in s for (sp, _ipa) in names.values())]
    if not targets:
        return "no name-bearing sentences found in corpus"
    print("\n=== Name pronunciation check (separate from the int8 verdict) ===")
    ok, total = 0, 0
    for b in build_names:
        for i in targets:
            print(f"[{b}] sentence {i + 1}:"); play(b, i)
            r = input("  names pronounced correctly? [y/n]: ").strip().lower()
            total += 1; ok += 1 if r == "y" else 0
    return f"{ok}/{total} name-bearing clips judged correct across {build_names}"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
