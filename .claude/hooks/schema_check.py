#!/usr/bin/env python3
"""The log schema is the Phase 2 contract. Check every touch of it.

Fires on writes under scribe/ and on any *.jsonl fixture. Validates that the
v1.3 field set the spec committed to is actually present - the fields that are
one line now and a painful migration later.
"""
import json
import re
import sys
from pathlib import Path

from _common import edited_path, hook_input, rel

REQUIRED_HEADER = {"type", "seq", "schema_version", "config_hash", "persona_version"}
REQUIRED_EVENT = {"type", "seq"}
MALANG_TURN_EXTRA = {"persona_version", "responded_to"}
SPEAKER_ENUM = {"waleed", "malang", "other", "unknown"}

p = edited_path(hook_input())
if p is None or not p.exists():
    sys.exit(0)

r = rel(p)
problems = []

# 1. JSONL fixtures must actually validate.
if p.suffix == ".jsonl":
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            if i == len(p.read_text().splitlines()):
                continue  # torn final line is legal (FR-10)
            problems.append(f"line {i}: not valid JSON, and not the final line")
            continue
        if i == 1:
            missing = REQUIRED_HEADER - ev.keys()
            if ev.get("type") != "header":
                problems.append("line 1 must be the `header` event (schema v1.3)")
            elif missing:
                problems.append(f"header is missing {sorted(missing)}")
        else:
            missing = REQUIRED_EVENT - ev.keys()
            if missing:
                problems.append(f"line {i}: missing {sorted(missing)}")
        if ev.get("type") == "turn":
            if ev.get("speaker") not in SPEAKER_ENUM:
                problems.append(
                    f"line {i}: speaker={ev.get('speaker')!r} is not in the v1.3 enum "
                    f"{sorted(SPEAKER_ENUM)}. Other voices in the room must never be "
                    "silently attributed to Waleed - that is corpus poisoning."
                )
            if ev.get("speaker") == "malang":
                m = MALANG_TURN_EXTRA - ev.keys()
                if m:
                    problems.append(f"line {i}: Malang turn missing {sorted(m)}")

# 2. The writer/schema modules must know about the whole v1.3 field set.
if r.startswith("malang/scribe/") and p.suffix == ".py":
    src = p.read_text(encoding="utf-8", errors="ignore")
    if "schema" in p.name or "writer" in p.name:
        for field in ("seq", "schema_version", "persona_version", "responded_to",
                      "config_hash", "amend"):
            if field not in src:
                problems.append(
                    f"`{field}` does not appear in {r}. Spec v1.3 added it to the "
                    "Phase 2 contract; one line now, a migration later."
                )
        if "fsync" not in src and "writer" in p.name:
            problems.append(
                "os.fsync is absent from the writer. FR-10: flush() alone is not "
                "durability. Page cache is not the disk."
            )

if problems:
    print(f"SCHEMA CONTRACT CHECK — {r}\n", file=sys.stderr)
    for x in problems:
        print(f"  - {x}", file=sys.stderr)
    print(
        "\nSpec section 6.1 is the Phase 2 input format. Phase 2 must never require "
        "rewriting Phase 1 records (C-7).",
        file=sys.stderr,
    )
    sys.exit(2)
