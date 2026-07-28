#!/usr/bin/env python3
"""Preflight for /pass-feature. Refuses to ship what should not ship."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATHS = [
    (re.compile(r"^memory/"), "a conversation record"),
    (re.compile(r"\.wav$"), "an audio file"),
    (re.compile(r"\.jsonl$"), "a session log"),
    (re.compile(r"^\.env"), "an environment file"),
    (re.compile(r"\.onnx$|\.pt$"), "a model artifact (too large for git)"),
]
SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")


def git(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], capture_output=True, text=True, timeout=60)


def die(msg: str, hint: str = "") -> None:
    print(msg, file=sys.stderr)
    if hint:
        print("\n" + hint, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if git("rev-parse", "--git-dir").returncode != 0:
        die("Not a git repository.")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch in ("main", "master", "HEAD"):
        die(
            f"You are on `{branch}`. There is no feature to pass.",
            "Switch to the feature branch, or start one with /spec-creator.",
        )

    base = None
    for cand in ("main", "master"):
        if git("show-ref", "--verify", f"refs/heads/{cand}").returncode == 0:
            base = cand
            break
    if not base:
        die("Could not find a main or master branch.")

    # --- spec must exist -----------------------------------------------------
    slug = branch.split("/", 1)[-1]
    slug = re.sub(r"-\d+$", "", slug)  # strip the collision suffix
    spec_dir = Path(".claude/specs")
    matches = sorted(spec_dir.glob(f"{slug}*.md")) if spec_dir.exists() else []
    if not matches:
        die(
            f"No spec found in .claude/specs/ matching `{slug}`.",
            "Every feature ships with the spec it was built from. If this branch "
            "predates /spec-creator, write the spec now — a merged feature with no "
            "spec is a feature nobody can review later.",
        )
    spec_path = matches[0]

    # --- what changed --------------------------------------------------------
    mb = git("merge-base", base, "HEAD").stdout.strip()
    committed = git("diff", "--name-only", f"{mb}...HEAD").stdout.split()
    uncommitted = [l[3:].strip() for l in git("status", "--porcelain").stdout.splitlines()]
    changed = sorted(set(committed) | set(uncommitted))

    if not changed:
        die(f"Nothing changed on `{branch}` relative to `{base}`. Nothing to pass.")

    # --- the record never enters git ----------------------------------------
    blocked = []
    for f in changed:
        for pat, what in FORBIDDEN_PATHS:
            if pat.search(f):
                blocked.append(f"{f} — {what}")
    if blocked:
        die(
            "BLOCKED: these must never be committed:\n\n"
            + "\n".join("    " + b for b in blocked),
            "The record is the product and it stays out of version control.\n"
            "Add them to .gitignore, then `git rm --cached <file>`.",
        )

    leaked = []
    for f in changed:
        p = Path(f)
        if p.is_file() and p.stat().st_size < 2_000_000:
            try:
                if SECRET.search(p.read_text(encoding="utf-8", errors="ignore")):
                    leaked.append(f)
            except OSError:
                pass
    if leaked:
        die(
            "BLOCKED: a live-looking API key is in:\n\n"
            + "\n".join("    " + f for f in leaked),
            "Rotate the key, then move it to the environment or DPAPI. Hard rule 6.",
        )

    warnings = []
    if git("remote").stdout.strip() == "":
        warnings.append("No git remote — push and PR steps will not work.")
    if any(f.endswith("malang-persona.md") for f in changed):
        warnings.append(
            "malang-persona.md changed — persona_version must be bumped AND the "
            "A-15 probes re-run before this merges (FR-21)."
        )
    if any("scribe/" in f or f.endswith(".jsonl") for f in changed):
        warnings.append(
            "The Scribe changed — confirm a real session still validates and that "
            "an older fixture still reads (C-7)."
        )

    print(json.dumps({
        "branch": branch,
        "base": base,
        "spec_path": str(spec_path).replace("\\", "/"),
        "changed_files": changed,
        "has_uncommitted": bool(uncommitted),
        "ahead": len(git("rev-list", f"{base}..HEAD").stdout.split()),
        "warnings": warnings,
    }, indent=2))


if __name__ == "__main__":
    main()