#!/usr/bin/env python3
"""PreToolUse gate: refuse to write a secret into a tracked file.

This one DENIES rather than warns. Hard rule 6: the key lives in the
environment or DPAPI, never in malang.toml, never in the repo.
"""
import json
import re
import sys

from _common import hook_input

PATTERNS = [
    (r"sk-ant-[A-Za-z0-9_\-]{10,}", "an Anthropic API key"),
    (r"(?i)\bapi[_-]?key\s*[:=]\s*[\"'][^\"'{$][^\"']{12,}[\"']", "a hardcoded API key"),
    (r"(?i)\b(secret|token|password)\s*[:=]\s*[\"'][^\"'{$][^\"']{12,}[\"']", "a hardcoded credential"),
]

data = hook_input()
ti = data.get("tool_input") or {}
blob = " ".join(
    str(ti.get(k, "")) for k in ("content", "new_string", "command", "file_path")
)

for pat, what in PATTERNS:
    if re.search(pat, blob):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Blocked: this write contains {what}. Malang hard rule 6 - "
                            "credentials come from the environment or Windows DPAPI, "
                            "never from malang.toml and never from a tracked file. "
                            "Read it with os.environ[...] instead."
                        ),
                    }
                }
            )
        )
        sys.exit(0)

sys.exit(0)
