#!/usr/bin/env python3
"""Git preflight for /spec-creator.

Order matters: the branch is prepared BEFORE the spec file is written, so the
spec is authored on its own feature branch and never lands loose on main.

Contract:
  argv[1]  raw feature argument, e.g. "P-1 - API latency probe"
  stdout   JSON summary on success
  exit 1   refuse to proceed, with a human reason on stderr
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=check, timeout=60
    )


def die(msg: str, hint: str = "") -> None:
    print(msg, file=sys.stderr)
    if hint:
        print("\n" + hint, file=sys.stderr)
    sys.exit(1)


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def parse(raw: str) -> tuple[str, str]:
    """'P-1 - API latency probe' -> ('P-1', 'API latency probe').

    Accepts em dash, en dash, hyphen, or colon as the separator. If no
    separator is present, the first whitespace-delimited token is the id.
    """
    raw = raw.strip().strip('"').strip("'")
    m = re.match(r"^\s*([A-Za-z]+[-\s]?[0-9]+(?:\.[0-9]+)?[a-z]?)\s*[—–\-:]+\s*(.+)$", raw)
    if m:
        return m.group(1).replace(" ", "-").upper(), m.group(2).strip()
    parts = raw.split(None, 1)
    if len(parts) == 2 and re.match(r"^[A-Za-z]+-?[0-9]", parts[0]):
        return parts[0].upper(), parts[1].strip()
    die(
        f"Could not parse a feature id and title from: {raw!r}",
        "Expected something like:  P-1 - API latency probe\n"
        "                          M1 - Scribe durability kit\n"
        "                          FR-19 - Backup and restore job",
    )
    raise SystemExit(1)  # unreachable, keeps type checkers happy


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        die("No feature given.", "Usage: /spec-creator P-1 - API latency probe")

    feature_id, title = parse(" ".join(sys.argv[1:]))
    slug = f"{slugify(feature_id)}-{slugify(title)}"

    if git("rev-parse", "--git-dir").returncode != 0:
        die(
            "Not a git repository.",
            "Run `git init` first. Malang's whole discipline is that the record "
            "survives — that starts with version control for the code that writes it.",
        )

    # ---- 1. refuse to move with a dirty tree -------------------------------
    dirty = git("status", "--porcelain").stdout.strip()
    if dirty:
        files = "\n".join("    " + l for l in dirty.splitlines()[:20])
        more = "" if len(dirty.splitlines()) <= 20 else f"\n    ... and {len(dirty.splitlines()) - 20} more"
        die(
            "STOPPED: you have uncommitted changes.\n\n" + files + more,
            "Switching branches now would drag this work onto the new branch.\n"
            "Commit it, or stash it, then run /spec-creator again:\n\n"
            "    git add -A && git commit -m \"wip: <what this was>\"\n"
            "    # or\n"
            "    git stash push -m \"before " + slug + "\"",
        )

    # ---- 2. work out the default branch ------------------------------------
    has_remote = bool(git("remote").stdout.strip())
    default = None
    if has_remote:
        r = git("symbolic-ref", "refs/remotes/origin/HEAD")
        if r.returncode == 0:
            default = r.stdout.strip().rsplit("/", 1)[-1]
    if not default:
        for cand in ("main", "master"):
            if git("show-ref", "--verify", f"refs/heads/{cand}").returncode == 0:
                default = cand
                break
    if not default:
        die(
            "Could not find a main or master branch.",
            "Create one, or edit DEFAULT_BRANCH handling in this script.",
        )

    notes: list[str] = []

    # ---- 3. refresh knowledge of existing branches -------------------------
    if has_remote:
        f = git("fetch", "origin", "--prune")
        if f.returncode != 0:
            notes.append("Could not reach origin (offline?) — branch-name collision "
                         "check used local branches only.")

    existing = set()
    for line in git("branch", "-a", "--format=%(refname:short)").stdout.splitlines():
        b = line.strip()
        existing.add(b.removeprefix("origin/") if b.startswith("origin/") else b)

    # ---- 4. pick a free branch name ----------------------------------------
    base = f"feat/{slug}"
    branch, n = base, 1
    while branch in existing:
        n += 1
        branch = f"{base}-{n}"
    if n > 1:
        notes.append(f"`{base}` already exists — using `{branch}` instead.")

    # ---- 5. main, pull, branch ---------------------------------------------
    co = git("checkout", default)
    if co.returncode != 0:
        die(f"Could not switch to {default}:\n{co.stderr.strip()}")

    if has_remote:
        pull = git("pull", "--ff-only", "origin", default)
        if pull.returncode != 0:
            notes.append(
                f"`git pull --ff-only origin {default}` failed — branching from the "
                f"local {default} instead. Reason: {pull.stderr.strip().splitlines()[-1] if pull.stderr.strip() else 'unknown'}"
            )
        else:
            notes.append(f"Pulled latest {default}.")
    else:
        notes.append("No git remote configured — branched from local " + default + ".")

    nb = git("checkout", "-b", branch)
    if nb.returncode != 0:
        die(f"Could not create branch {branch}:\n{nb.stderr.strip()}")

    spec_dir = Path(".claude/specs")
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f"{slugify(feature_id)}-{slugify(title)}.md"

    print(json.dumps({
        "feature_id": feature_id,
        "title": title,
        "slug": slug,
        "branch": branch,
        "base_branch": default,
        "spec_path": str(spec_path).replace("\\", "/"),
        "spec_exists": spec_path.exists(),
        "notes": notes,
    }, indent=2))


if __name__ == "__main__":
    main()