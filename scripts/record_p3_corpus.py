#!/usr/bin/env python3
"""Record the P-3 corpus on the production mic (spec section 3).

Walks the three registers in prompts.md and records each to a 16 kHz mono WAV
under corpus/p3/audio/ - 16 kHz mono at record time so no per-model resampling
ever confounds the WER (spec section 12 rule 2).

    python scripts/record_p3_corpus.py            # all three, in order
    python scripts/record_p3_corpus.py monologue  # just one

Needs the optional recorder dep: `uv sync --extra recorder` (sounddevice). This
writes audio only; it is not a measurement and imports no ASR engine. The raw
WAVs are git-ignored - they are your voice, not code.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

SAMPLE_RATE = 16000
REGISTERS = ("monologue", "read", "codeswitch")
AUDIO_DIR = Path("corpus/p3/audio")


def _record_one(name: str) -> None:
    import numpy as np
    import sounddevice as sd

    out = AUDIO_DIR / f"{name}.wav"
    if out.exists():
        if input(f"\n{out} exists. Overwrite? [y/N] ").strip().lower() != "y":
            print("  kept existing recording.")
            return

    print(f"\n=== {name} ===  (see corpus/p3/prompts.md for what to say)")
    input("Press Enter to START recording... ")
    print("Recording. Press Enter again to STOP.")

    frames: list = []
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        callback=lambda data, *_: frames.append(data.copy())):
        input()  # blocks here while the callback fills `frames`
    print("Stopped.")

    audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype="int16")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    secs = len(audio) / SAMPLE_RATE
    print(f"  wrote {out}  ({secs:.1f}s, 16 kHz mono)")
    if secs < 1.0:
        print("  WARNING: that was very short - did the mic capture anything?")


def main(argv) -> int:
    names = [a for a in argv if a in REGISTERS] or list(REGISTERS)
    try:
        import sounddevice  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"sounddevice not available ({exc}).\n"
              "Install it with:  uv sync --extra recorder\n"
              "Or record the three passages with any tool as 16 kHz mono WAVs at\n"
              f"  {AUDIO_DIR}/monologue.wav, read.wav, codeswitch.wav\n"
              "then hand-correct corpus/p3/reference/*.txt.", file=sys.stderr)
        return 2
    print("P-3 corpus recorder. Aim for ~10 min per register, ~30 min total.")
    for name in names:
        _record_one(name)
    print("\nDone. Now hand-correct corpus/p3/reference/*.txt and tag proper nouns in "
          "manifest.json, then run scripts/measure_p3_stt.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
