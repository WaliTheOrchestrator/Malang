#!/usr/bin/env python3
"""PostToolUse guard on the latency-critical path (wire from M3a onward).

HP10: it is easy to measure component latencies that sum to a number nobody
experiences. This does not measure anything - it refuses to let the hot path
acquire the constructs that quietly cost milliseconds.
"""
import re
import sys

from _common import edited_path, fail, hook_input, rel, strip_comments

HOT = ("malang/session/", "malang/speech/", "malang/ear/")

BANNED = [
    (r"\btime\.sleep\s*\(", "time.sleep on the hot path blocks the asyncio loop. "
     "Use asyncio.sleep, or a proper event."),
    (r"\bprint\s*\(", "print() on the hot path does synchronous I/O. Use the "
     "structured logger, off the latency path."),
    (r"requests\.(get|post)", "blocking HTTP on the hot path. The Claude client is "
     "async and cancellable per turn_id (HP3)."),
    (r"\.join\s*\(\s*\)\s*$", "a blocking thread join on the hot path."),
    (r"asyncio\.get_event_loop\(\)\.run_until_complete", "nested loop execution "
     "inside a running loop - this is how cancellation correctness dies (HP3)."),
]

CANCEL_HINT = re.compile(r"async def \w+|await ")

p = edited_path(hook_input())
if p is None or not p.exists() or p.suffix != ".py":
    sys.exit(0)
r = rel(p)
if not any(r.startswith(h) for h in HOT):
    sys.exit(0)

src = strip_comments(p.read_text(encoding="utf-8", errors="ignore"))
v = [f"{r}: {msg}" for pat, msg in BANNED if re.search(pat, src)]

# HP3: every piece of in-flight work carries a turn_id and drops stale output.
if CANCEL_HINT.search(src) and "turn_id" not in src and "cancel" in src:
    v.append(
        f"{r}: cancellation logic without turn_id. HP3's rule is one authority and "
        "one `if` everywhere: any output arriving with a stale turn_id is dropped "
        "at the boundary. Orphaned tasks answer questions nobody asked."
    )

fail(v, "LATENCY / CANCELLATION PATH GUARD (HP3, HP4, HP10)")
