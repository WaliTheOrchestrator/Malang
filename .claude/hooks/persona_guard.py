#!/usr/bin/env python3
"""Guard malang-persona.md — the file where three separate things break at once.

Editing Block 1 does all of the following, silently, unless caught:
  1. invalidates the prompt cache for every subsequent turn (prefix caching)
  2. leaves persona_version stale, so the log lies about which Malang spoke
  3. invalidates the last A-15 probe run (FR-21: re-validate on any change)

It also re-checks the thing that started all this: Block 1 must be LONGER than
the fast tier's minimum cacheable prefix, or it caches nothing at all - silently,
with no error from the API.
"""
import re
import sys
from pathlib import Path

from _common import edited_path, hook_input, project_dir

# Verified against the live API in M0 - update here when it moves.
FAST_TIER_MIN_TOKENS = 4096
TOKENS_PER_CHAR = 1 / 3.7  # rough English estimate; M0 replaces with a real count

p = edited_path(hook_input())
if p is None or p.name != "malang-persona.md" or not p.exists():
    sys.exit(0)

text = p.read_text(encoding="utf-8", errors="ignore")
problems = []

m = re.search(r"persona_version:\s*([0-9]+\.[0-9]+)", text)
if not m:
    problems.append("persona_version is missing from the header. Every Malang turn "
                    "event stamps it; without it the record cannot say who spoke.")
else:
    version = m.group(1)
    state = project_dir() / ".claude" / ".persona_state"
    prev = state.read_text().strip() if state.exists() else ""
    body_hash = str(abs(hash(text)))
    if prev and not prev.startswith(version + ":"):
        pass  # version changed: good, that is the expected path
    elif prev and prev != f"{version}:{body_hash}":
        problems.append(
            f"The file changed but persona_version is still {version}. "
            "Versioning rule 1: any edit bumps the version. Bump it, and note "
            "what changed in the header."
        )
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(f"{version}:{body_hash}")

# Block 1 length - the cache-minimum trap from the v1.3.1 round.
blk = re.search(r"\*\*Block 1(.{0,400}?)\*\*(.*?)(?=\*\*Block 2)", text, re.S)
if blk:
    est = int(len(blk.group(2)) * TOKENS_PER_CHAR)
    if est < FAST_TIER_MIN_TOKENS:
        problems.append(
            f"Block 1 is roughly {est} tokens, under the ~{FAST_TIER_MIN_TOKENS}-token "
            "minimum cacheable prefix on the fast tier. Below the minimum, NOTHING "
            "caches and no error is returned - the M4 >=80% gate and the cost model "
            "both break quietly. Block 1 must be charter + the full Part II portrait."
        )

if problems:
    print("PERSONA GUARD (FR-21 / prompt-cache discipline)\n", file=sys.stderr)
    for x in problems:
        print(f"  - {x}", file=sys.stderr)
    print(
        "\nAlso remember: any edit here invalidates the last A-15 probe run. "
        "Re-run the probes before this persona speaks in daily use.",
        file=sys.stderr,
    )
    sys.exit(2)
