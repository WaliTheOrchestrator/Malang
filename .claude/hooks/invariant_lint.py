#!/usr/bin/env python3
"""Malang invariant lint — the spec's hard rules, enforced as code.

Wired to PostToolUse(Write|Edit) and to Stop (with --full).
Every rule below cites the document that created it. If a rule is wrong,
change the SPEC first, then change this file — never the other way round.
"""
import re
import sys
from pathlib import Path

from _common import edited_path, fail, hook_input, project_dir, rel, strip_comments

# ---------------------------------------------------------------- rule table
# (path_glob_prefix, forbidden_regex, message)
RULES = [
    # Hard rule 3 / D-13 / FR-17: the Session Engine reads nothing from memory/.
    (
        "malang/session/",
        r"""(memory/|memory_root|MEMORY_ROOT|["']memory["'])""",
        "HARD RULE 3 violated: the Session Engine must read NOTHING from memory/. "
        "The only exception is the >=100-token continuity string, handed in as a "
        "plain argument at session open (FR-17) - it is passed IN, never read here.",
    ),
    (
        "malang/session/",
        r"\bopen\s*\(|\bPath\s*\(.*\)\.read_|json\.load\s*\(",
        "HARD RULE 3 (scope creep guard): the Session Engine is doing disk I/O. "
        "Phase 1's stated risk is 'just a little retrieval...'. Config comes from "
        "the loader; continuity comes in as a string. Justify or remove.",
    ),
    # C-8: no code path transcribes idle audio. Enforced by module boundary.
    (
        "malang/ear/",
        r"stt_live|Moonshine|moonshine|transcribe|Parakeet|parakeet",
        "C-8 violated: the Ear must have NO path to STT. Idle-state transcription "
        "is prohibited structurally, not disabled by an `if`. The Ear owns the mic "
        "in IDLE and hands it over at SUMMONED - it never imports a recognizer.",
    ),
    # FR-10 / D-12 / HP9: the record is append-only and fsync'd.
    (
        "malang/scribe/writer.py",
        r"""open\s*\([^)]*["'](w|r\+|w\+)["']|\.truncate\s*\(|\.seek\s*\(""",
        "FR-10 violated: session.jsonl is APPEND-ONLY. No 'w'/'r+' modes, no "
        "truncate, no seek. Corrections are `amend` events, never rewrites.",
    ),
    # C-9 / D-4: one voice identity, everywhere.
    (
        "malang/",
        r"pyttsx3|gTTS|edge_tts|espeak|SAPI|win32com\.client.*Speech",
        "C-9 violated: a second TTS engine means a second voice means broken "
        "presence. Every audible byte is the P-6 Kokoro voice (or its documented "
        "fallback), including cues and reflex clips.",
    ),
    # Hard rule 6: the API key never lands in the config file or the repo.
    (
        "",
        r"sk-ant-[A-Za-z0-9_\-]{10,}",
        "HARD RULE 6 violated: a live-looking Anthropic key is in a tracked file. "
        "Keys come from the environment or Windows DPAPI. Rotate it now.",
    ),
    # HP4: the audio callback moves bytes and nothing else.
    (
        "malang/speech/audio_io.py",
        r"def\s+\w*callback\w*\([\s\S]{0,1200}?(logging\.|logger\.|print\(|json\.|"
        r"np\.zeros|np\.empty|np\.array|\.append\(|time\.sleep)",
        "HP4 violated: the audio callback allocates, logs, or blocks. It has a hard "
        "10ms deadline under the GIL. It may ONLY move bytes to/from preallocated "
        "ring buffers - no allocation, no locks, no logging.",
    ),
    # Status page: read-only, loopback only, no control paths (design M6.5).
    (
        "malang/status/",
        r"""0\.0\.0\.0|["']::["']|host\s*=\s*["'](?!127\.0\.0\.1)""",
        "M6.5 violated: the status page never leaves 127.0.0.1. A dashboard that "
        "can be reached from the network is a new failure surface on a machine "
        "holding every private conversation you have ever had.",
    ),
    (
        "malang/status/",
        r"@(app|router)\.(post|put|delete|patch)|def\s+(start|stop|restart|set_)",
        "M6.5 violated: the status page is READ-ONLY. 'A dashboard that can touch "
        "the pipeline is a new failure source - this one can die and Malang "
        "doesn't notice.' No control paths.",
    ),
]

# Files that are allowed to mention memory/ inside session/: none. Keep it honest.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".claude", "memory"}


def check_file(path: Path, root: Path) -> list[str]:
    r = rel(path)
    if not r.endswith((".py", ".toml", ".json", ".yaml", ".yml")):
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    body = strip_comments(raw)
    out = []
    for prefix, pattern, msg in RULES:
        if prefix and not r.startswith(prefix):
            continue
        if re.search(pattern, body):
            out.append(f"{r}\n      {msg}")
    return out


def main() -> None:
    root = project_dir()
    full = "--full" in sys.argv

    if full:
        targets = [
            p
            for p in root.rglob("*")
            if p.is_file() and not (SKIP_DIRS & set(p.relative_to(root).parts))
        ]
    else:
        p = edited_path(hook_input())
        if p is None or not p.exists():
            sys.exit(0)
        targets = [p]

    violations: list[str] = []
    for t in targets:
        violations.extend(check_file(t, root))

    fail(violations, "MALANG INVARIANT VIOLATION (spec hard rules)")


if __name__ == "__main__":
    main()
