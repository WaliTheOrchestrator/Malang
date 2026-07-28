---
name: pass-feature
description: Ship a completed Malang feature — verify the Definition of Done, commit, push, open a PR via GitHub MCP, merge it, and clean up the local branch. Use only when a feature branch is believed finished and its spec's Definition of Done is genuinely met.
argument-hint: (no arguments — operates on the current branch)
---

# Pass a feature

Close out the branch `/spec-creator` opened. Argument, if any: **$ARGUMENTS**

This skill merges to main. It is the only skill here that destroys something
(the branch) and changes the trunk. Treat every gate below as load-bearing —
they exist so that "done" means done, not "I stopped working on it."

---

## Step 1 — Preflight

```
python .claude/skills/pass-feature/scripts/preflight.py
```

Refuses and explains itself if:

- you are on `main` / `master` (nothing to pass)
- the branch has no matching spec in `.claude/specs/`
- a changed file is a conversation record, an audio file, or contains a
  credential — **the record never enters git**

On success it prints JSON: `branch`, `spec_path`, `base`, `changed_files`,
`has_uncommitted`, `ahead`, `warnings`.

Read the spec at `spec_path` now. You need its Overview, its Definition of
Done, and its Test plan for the PR body.

---

## Step 2 — Verify the Definition of Done, honestly

**This is the step that matters.** Do not copy the checkboxes from the spec.
Run them, and record what you actually observed.

```
python .claude/hooks/invariant_lint.py --full
pytest -q
```

Then check, by reading:

| Check | Where the evidence is |
|---|---|
| Milestone exit test passed, with a number | `docs/milestones/<M>.md` or the spec |
| A session written by this code validates | run the validator against a real fixture |
| Reviewers run, BLOCKING findings resolved | the milestone note |
| Measurement gate ruling recorded, if a gate was used | `docs/m0-measurements.md` — no `____` left |
| Config keys documented with defaults | `malang.toml` |
| `persona_version` bumped and A-15 re-run, if the persona changed | `malang-persona.md` header, `docs/probes/` |
| **Usable that evening** | say plainly whether the system works tonight |

**If any check fails, stop here.** Report which one, and do not commit. A
feature that merges with a red gate is how the spec becomes fiction — and this
project's only real defence is that its documents are true.

If a box in the spec is genuinely not applicable, mark it `n/a` in the spec
file with a one-line reason. Never silently tick it.

---

## Step 3 — Commit

Only if Step 2 is fully green. Stage deliberately — `git add -A` after a long
session picks up scratch files.

Commit message shape (matches `/milestone-close`):

```
<ID>: <Title>

<one sentence on what now works that did not before>

Exit test: <what was measured, with the number>
Reviewers: <BLOCKING findings resolved, or "clean">
Spec: .claude/specs/<file>.md
Deferred: <what, and the gate that would bring it back — or omit>
```

Then push:

```
git push -u origin <branch>
```

---

## Step 4 — Open the PR (GitHub MCP)

Title: `<ID> — <Title>`

Body, exactly these four sections:

```markdown
## What this does

<One short paragraph, lifted from the spec's Overview. Say what is now
possible that was not before — not a list of files.>

## Changes

| File | Change |
|---|---|
| `path/to/file.py` | one line, what it does now |

<Every changed file. If a file changed only cosmetically, say so — a reviewer
scanning this should be able to skip it.>

## Definition of done

<Copy the spec's Definition of Done, with each box reflecting what Step 2
ACTUALLY observed. Include the evidence inline.>

- [x] Milestone exit test passes — TTFT p50 = 612ms (gate: ≤800ms)
- [x] `invariant_lint --full` clean
- [x] `pytest -q` — 34 passed
- [ ] n/a — no schema impact

## How to test

<Numbered, runnable. Commands for the automatable parts; for anything needing
the real mic, speakers, or battery, a numbered manual procedure with the
expected observation written down. Someone tired at 11pm should be able to
follow it.>

Spec: `.claude/specs/<file>.md`
```

---

## Step 5 — Merge

Merge via GitHub MCP, **squash merge**. One commit per feature on main matches
the milestone structure and keeps the trunk readable a year from now.

Delete the remote branch as part of the merge.

Do not merge if the PR reports a conflict — stop, report it, and let the user
decide. Never resolve a main-branch conflict unattended.

---

## Step 6 — Clean up

```
python .claude/skills/pass-feature/scripts/cleanup.py <branch>
```

Switches to the base branch, pulls, and deletes the local branch with `-d`
(not `-D`) so git itself refuses if anything is unmerged. Prunes stale remotes.

Then update the project's record of itself:

- Set the spec's `Status:` to `done`.
- Tick the milestone checkbox in `malang-phase1-build-plan.md` if this
  completed one.
- If a measurement gate ruled against a spec assumption, **amend the spec now.**
  The spec wins over the build plan, so the spec has to be true.

---

## Step 7 — Report

```
SHIPPED — <ID> <Title>

PR:        #<n> (squash-merged)
Commit:    <sha> on <base>
Branch:    feat/<slug> deleted, local and remote

Verified:  exit test <number> · invariant lint clean · <n> tests
Spec:      .claude/specs/<file>.md → status: done
Milestone: M-n <ticked | still open>

Next:      <the next unticked item in the build plan>
```

---

## Rules

1. **Never run this on `main`.** Preflight enforces it.
2. **Never commit `memory/`, `*.wav`, `*.jsonl`, or a credential.** Preflight
   scans for it. If it fires, that is not a false positive to work around.
3. **Never tick a Definition-of-Done box you did not verify this run.** The
   whole value of the box is that it is true.
4. **Red gate means stop.** No merging past a failing check, no "I'll fix it on
   main". Main stays shippable.
5. **Squash merge, always.** One commit per feature.
6. **Never force-push.** Never `git branch -D`. Never resolve a conflict on
   main without asking.
7. **If the persona changed, the A-15 probes must have been re-run.** FR-21 —
   the character is the deliverable, not a side effect.
8. **Leave main usable.** If this merge leaves Malang broken overnight, it was
   not ready to pass.