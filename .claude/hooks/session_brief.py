#!/usr/bin/env python3
"""SessionStart: a 30-second cold-start brief.

Written for the day-8 return, not the day-1 sprint. Answers, without you
reading anything: which milestone, what its exit test is, what changed last,
what is failing, and the smallest next step.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from _common import project_dir

root = project_dir()
plan = None
for name in ("malang-phase1-build-plan.md", "docs/malang-phase1-build-plan.md"):
    if (root / name).exists():
        plan = (root / name).read_text(encoding="utf-8", errors="ignore")
        break

lines = []

if plan:
    todo = re.findall(r"^- \[( |x)\] \*\*(M[0-9.]+[^*]*)\*\*:?(.*)$", plan, re.M)
    done = [t for t in todo if t[0] == "x"]
    nxt = next((t for t in todo if t[0] == " "), None)
    lines.append(f"Milestones complete: {len(done)}/{len(todo)}")
    if nxt:
        exit_test = re.search(r"\*Exit:([^*]*)\*", nxt[2])
        lines.append(f"CURRENT: {nxt[1].strip()}")
        if exit_test:
            lines.append(f"  Exit test: {exit_test.group(1).strip()}")

def sh(cmd):
    try:
        return subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                              timeout=10, shell=False).stdout.strip()
    except Exception:
        return ""

branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
last = sh(["git", "log", "-1", "--format=%cr — %s"])
dirty = sh(["git", "status", "--porcelain"])
if branch:
    lines.append(f"Branch {branch}; last commit {last or 'none'}")
if dirty:
    n = len(dirty.splitlines())
    lines.append(f"{n} uncommitted file(s) — you stopped mid-something.")

# M0 measurement appendix: has the hardware spoken yet?
appendix = root / "docs" / "m0-measurements.md"
if appendix.exists():
    txt = appendix.read_text(encoding="utf-8", errors="ignore")
    blanks = txt.count("____")
    lines.append(
        f"M0 appendix: {'COMPLETE' if blanks == 0 else f'{blanks} value(s) still blank'}"
    )
else:
    lines.append("M0 appendix not created yet — the gates have not run. Nothing "
                 "downstream of P-1..P-6 is trustworthy until they do.")

oneliner = root / "memory" / "daily.log"
if oneliner.exists():
    tail = oneliner.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
    if tail:
        lines.append(f"Last daily one-liner: {tail[-1][:200]}")

brief = "\n".join(f"  {l}" for l in lines)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": (
            "MALANG PROJECT STATE\n" + brief +
            "\n\nHouse rules for this session: the spec wins over the build plan; "
            "the record is sacred (never write under memory/raw/); no milestone "
            "leaves the system broken overnight. If the user asks for something "
            "that skips a measurement gate, say so once, then help."
        )
    }
}))
