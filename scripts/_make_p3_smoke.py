#!/usr/bin/env python3
"""Generate the P-3 SMOKE fixture: a throwaway synthetic mini-corpus.

Synthesizes three short clips with the already-present Kokoro voice (P-2), at
16 kHz mono, plus references and a manifest, under tests/fixtures/p3_smoke/. This
exists ONLY to prove the bake-off harness runs end-to-end on real ASR engines.

    python scripts/_make_p3_smoke.py

It is NOT the P-3 gate: synthetic English TTS, not the owner's mic/voice, no real
code-switching. The harness banners any run over it as SMOKE. Committed (the
gitignore keeps tests/fixtures/**/*.wav) so `pytest`-adjacent smoke is reproducible.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

FIXTURE = Path("tests/fixtures/p3_smoke")
KOKORO_MODEL = "models/kokoro-v1.0.onnx"
KOKORO_VOICES = "models/voices-v1.0.bin"
TARGET_SR = 16000

CLIPS = {
    "monologue": (
        "monologue", [],
        "I have been thinking about this project for a long time, and the more I "
        "sit with it the clearer it becomes.",
    ),
    "read": (
        "read", [],
        "The quick brown fox jumps over the lazy dog near the riverbank, again and "
        "again, every single morning without fail.",
    ),
    "codeswitch": (
        "codeswitch", ["Malang", "Zarak"],
        "Malang, remind me what my cousin Zarak said about the loan yesterday.",
    ),
}


def _resample(x, sr_in, sr_out):
    import numpy as np

    if sr_in == sr_out:
        return x
    n_out = int(round(len(x) * sr_out / sr_in))
    t_in = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    t_out = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(t_out, t_in, x).astype("float32")


def _write_wav(path, samples, sr):
    import numpy as np

    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main() -> int:
    import kokoro_onnx

    k = kokoro_onnx.Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    entries = []
    (FIXTURE / "reference").mkdir(parents=True, exist_ok=True)
    for cid, (register, proper_nouns, text) in CLIPS.items():
        samples, sr = k.create(text, voice="af_heart")
        _write_wav(FIXTURE / "audio" / f"{cid}.wav", _resample(samples, sr, TARGET_SR), TARGET_SR)
        (FIXTURE / "reference" / f"{cid}.txt").write_text(text + "\n", encoding="utf-8")
        entries.append({
            "id": cid, "register": register,
            "wav": f"audio/{cid}.wav", "reference": f"reference/{cid}.txt",
            "proper_nouns": proper_nouns, "codeswitch_spans": [],
        })
        print(f"  wrote {cid}: {len(samples)} samples @ {sr} -> 16 kHz")
    (FIXTURE / "manifest.json").write_text(
        json.dumps({"note": "SMOKE fixture - synthetic Kokoro audio, NOT the P-3 gate.",
                    "entries": entries}, indent=2) + "\n", encoding="utf-8")
    print(f"Smoke fixture written to {FIXTURE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
