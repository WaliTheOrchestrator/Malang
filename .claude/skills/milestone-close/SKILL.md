---
name: milestone-close
description: Close a Malang milestone properly — run its exit test, run the full review gauntlet in parallel, verify the invariants and the record, update the build plan, and commit. Use whenever a milestone's work is believed finished.
---

# Close a milestone

A milestone is not done when the code works. It is done when its **exit test**
passes, the reviewers are quiet, and the system is usable that evening.

## 1. Restate the exit test

Read the current milestone's exit test from the build plan and quote it back.
Then say plainly whether it passed, and on what evidence. Not "it should" — what
was observed, on the real machine.

If the exit test cannot be run yet (missing hardware, an unmeasured gate), the
milestone is **not** closeable. Say so and stop.

## 2. Run the gauntlet in parallel

One message, all applicable reviewers at once:

- **spec-guardian** — always
- **code-quality** — always
- **security-review** — always at a milestone boundary
- **latency-auditor** — from M3a onward
- **chaos-engineer** — for M1, M3b, M6, and any milestone that added a failure path

Resolve every BLOCKING finding. Record DRIFT findings in the milestone note.

## 3. Verify the invariants directly

```
python .claude/hooks/invariant_lint.py --full
pytest -q
```

Plus, by hand, the three that matter most and are easiest to let slip:

- a session written by the current code **validates against the schema**
- the backup job ran, and the backup age in the daily one-liner is fresh
- `git status` shows no secret, no `memory/` content, no WAV staged

## 4. Update the record of the project

- Tick the milestone box in the build plan.
- Append to `docs/milestones/<M>.md`: what shipped, what the exit test measured,
  what was deferred and why, what the reviewers flagged and what you did about it.
- If a measurement gate ruled differently than the spec assumed, amend the spec
  now — not later. The spec wins over the build plan, so the spec has to be true.

## 5. Commit

One commit per milestone, message in this shape:

```
M<n>: <deliverable>

Exit test: <what was measured, with the number>
Reviewers: <blocking findings resolved>
Deferred: <what, and the gate that would bring it back>
```

## 6. The question that actually matters

**Is the system usable tonight?** Build-plan hard rule 2. If this milestone left
Malang broken, the milestone is not closed — put the half-finished part behind a
default-off flag and close it properly.
