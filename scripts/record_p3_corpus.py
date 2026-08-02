#!/usr/bin/env python3
"""Record the P-3 corpus on the production mic (spec section 3).

Records each register to a 16 kHz mono WAV under corpus/p3/audio/ - 16 kHz mono at
record time so no per-model resampling ever confounds the WER (spec section 12 rule 2).

Two modes:
  Fixed duration (best when launched from a non-interactive shell, e.g. Claude's `!`):
    python scripts/record_p3_corpus.py read --seconds 150 --overwrite
    -> waits `--lead` seconds (default 4), then records for exactly N seconds.
  Interactive (a real terminal):
    python scripts/record_p3_corpus.py read
    -> Enter to start, Enter to stop.

Needs the optional recorder dep: `uv sync --extra recorder` (sounddevice). Writes
audio only; imports no ASR engine. The raw WAVs are git-ignored - your voice, not code.
"""
from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

SAMPLE_RATE = 16000
REGISTERS = ("monologue", "read", "codeswitch")
AUDIO_DIR = Path("corpus/p3/audio")
SILENCE_PEAK = 200  # int16 peak below this ~ the mic captured nothing


def _write_wav(out: Path, audio) -> float:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return len(audio) / SAMPLE_RATE


def _record_one(name: str, seconds: float | None, lead: int, overwrite: bool) -> None:
    import numpy as np
    import sounddevice as sd

    out = AUDIO_DIR / f"{name}.wav"
    if out.exists() and not overwrite:
        if input(f"\n{out} exists. Overwrite? [y/N] ").strip().lower() != "y":
            print("  kept existing recording.")
            return

    print(f"\n=== {name} ===  (read the passage the assistant gave you)", flush=True)
    if seconds is not None:
        for i in range(lead, 0, -1):
            print(f"  starting in {i}...", flush=True)
            time.sleep(1)
        print(f"  RECORDING NOW for {seconds:.0f}s - read at a normal pace.", flush=True)
        audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                       channels=1, dtype="int16")
        sd.wait()
    else:
        input("Press Enter to START recording... ")
        print("Recording. Press Enter again to STOP.", flush=True)
        frames: list = []
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            callback=lambda data, *_: frames.append(data.copy())):
            input()
        audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype="int16")

    secs = _write_wav(out, audio)
    peak = int(np.abs(audio).max()) if len(audio) else 0
    print(f"  wrote {out}  ({secs:.1f}s, 16 kHz mono, peak={peak})", flush=True)
    if peak < SILENCE_PEAK:
        print("  WARNING: near-silent - check the input device / mic permissions.", flush=True)
    elif secs < 1.0:
        print("  WARNING: very short - did you start reading in time?", flush=True)


def main(argv) -> int:
    ap = argparse.ArgumentParser(prog="record_p3_corpus.py")
    ap.add_argument("names", nargs="*", choices=REGISTERS, default=list(REGISTERS),
                    help="Registers to record (default: all three, in order).")
    ap.add_argument("--seconds", type=float, default=None,
                    help="Fixed-duration mode: record exactly N seconds (no Enter needed).")
    ap.add_argument("--lead", type=int, default=4,
                    help="Seconds of lead-in before fixed-duration recording (default: 4).")
    ap.add_argument("--overwrite", action="store_true",
                    help="Overwrite an existing WAV without asking.")
    args = ap.parse_args(argv)

    names = args.names if isinstance(args.names, list) and args.names else list(REGISTERS)
    names = [n for n in names if n in REGISTERS] or list(REGISTERS)
    try:
        import sounddevice  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"sounddevice not available ({exc}).\n"
              "Install it with:  uv sync --extra recorder", file=sys.stderr)
        return 2
    for name in names:
        _record_one(name, args.seconds, args.lead, args.overwrite)
    print("\nDone recording the requested register(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
