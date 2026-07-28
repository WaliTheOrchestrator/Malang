"""Shared helpers for Malang's Claude Code hooks.

Hook contract used here:
  - input arrives as JSON on stdin
  - exit 0  = silent pass
  - exit 2  = stderr is shown to Claude as feedback (it will react and fix)
  - any other nonzero = non-blocking error, shown to you
"""
import json
import os
import sys
from pathlib import Path


def hook_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def edited_path(data: dict) -> Path | None:
    ti = data.get("tool_input") or {}
    p = ti.get("file_path") or ti.get("notebook_path")
    return Path(p) if p else None


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(project_dir())).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def fail(violations: list[str], header: str) -> None:
    """Exit 2 so Claude sees the violation and repairs it in the same turn."""
    if not violations:
        sys.exit(0)
    print(f"{header}\n", file=sys.stderr)
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    print(
        "\nThese are project invariants from malang-phase1-spec.md and the build "
        "plan's hard rules. Fix the code now; do not suppress the check.",
        file=sys.stderr,
    )
    sys.exit(2)


def strip_comments(src: str) -> str:
    """Crude but adequate: drop full-line comments and docstring-ish lines so the
    invariant greps don't fire on prose that merely *discusses* a rule."""
    out = []
    in_doc = False
    for line in src.splitlines():
        s = line.strip()
        if s.count('"""') == 1 or s.count("'''") == 1:
            in_doc = not in_doc
            continue
        if in_doc or s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
            continue
        out.append(line)
    return "\n".join(out)
