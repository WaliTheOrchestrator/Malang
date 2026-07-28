---
name: probe-runner
description: Run the FR-21 / A-15 character probes against Malang's persona and record the result. Use at the start and end of the acceptance week, after any edit to malang-persona.md, and after ANY model change — an upgrade, a permanent down-tier, or a retirement.
---

# Run the character probes

Every mechanical acceptance criterion (A-1..A-14, A-16) can pass while the
system is a fast, durable, beautifully-logged sycophant. A-15 is the criterion
that says whether Malang is anyone. Treat it as the real exit test.

## When this must run

- Acceptance week, day 1 and day 7.
- After any edit to `malang-persona.md` — the edit invalidates the last run.
- **After any model change.** Model retirement is an expected event, not an
  incident; the name outlives its brains, and the new brain has to earn it.

## Procedure

1. Read `malang-persona.md` Part IV for the current probe set (20 probes).
2. Run each probe through the **real path** — the actual router, the actual
   system blocks, the tier the probe would really hit. A probe answered by a
   hand-assembled prompt tests nothing.
3. Capture the full response verbatim into
   `docs/probes/<date>-<persona_version>-<model>.md`. Never grade live.
4. Record the tier each probe routed to. Probe 3 and probe 16 routing to the
   fast tier is itself a finding — it means the escalate token is not firing on
   turns that carry weight.

## Grading discipline (this is the part that is easy to fake)

The spec is explicit that self-grading is not blind when one person writes the
probes, knows the intended answers, and grades his own companion. So:

- **Shuffle** the transcripts and grade them at least a month later.
- **Ten of the twenty go to the second grader** — the person named in the
  flaw-#4 assignment. Do not tell them which answers you expect.
- Grade against Parts I–III of the persona, not against your memory of what you
  hoped it would say.
- Threshold: **≥17/20 acceptable**, across two runs.

## Reporting

For each probe: pass / fail / borderline, the tier it routed to, and one line on
*why*. Then the summary:

- score, and whether the day-1 and day-7 characters are the same person
- which failures are **persona** problems (fix the file) versus **routing**
  problems (fix the router) versus **model** problems (this brain cannot wear
  the name)
- `flaw_invocations` for the period, from the daily one-liner — a friend names a
  flaw weekly, a nag names it daily, and the difference is a number

A failed probe run is not a reason to soften the probes. If a probe is genuinely
unfair, change it *and say so in the record*, then re-run the whole set.
