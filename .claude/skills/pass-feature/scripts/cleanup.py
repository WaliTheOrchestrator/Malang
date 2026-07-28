#!/usr/bin/env python3
"""Post-merge cleanup for /pass-feature. Safe by construction: `-d`, never `-D`."""
from __future__ import annotations

import subprocess
import sys


def git(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], capture_output=True, text=True, timeout=60)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: cleanup.py <feature-branch>", file=sys.stderr)
        sys.exit(1)
    branch = sys.argv[1]

    base = next(
        (c for c in ("main", "master")
         if git("show-ref", "--verify", f"refs/heads/{c}").returncode == 0),
        None,
    )
    if not base:
        print("No main or master branch found.", file=sys.stderr)
        sys.exit(1)

    out = []

    co = git("checkout", base)
    if co.returncode != 0:
        print(f"Could not switch to {base}:\n{co.stderr}", file=sys.stderr)
        sys.exit(1)
    out.append(f"switched to {base}")

    if git("remote").stdout.strip():
        pull = git("pull", "--ff-only", "origin", base)
        out.append(f"pulled {base}" if pull.returncode == 0
                   else f"WARNING: pull failed — {pull.stderr.strip().splitlines()[-1]}")
        git("fetch", "--prune", "origin")
        out.append("pruned stale remote branches")

    # -d refuses if the branch is not fully merged. That refusal is the feature.
    d = git("branch", "-d", branch)
    if d.returncode == 0:
        out.append(f"deleted local branch {branch}")
    else:
        out.append(
            f"KEPT local branch {branch} — git says it is not fully merged into "
            f"{base}. Do NOT force-delete. Check whether the squash-merge landed."
        )

    print("\n".join("  " + l for l in out))


if __name__ == "__main__":
    main()