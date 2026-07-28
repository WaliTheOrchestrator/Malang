---
name: new-module
description: Implement one Malang module end to end, spec-first. Use when starting any module under malang/ — ear, session, speech, mind, scribe, afterword, text, status. Walks from the governing FRs through the contract test to the implementation and the review gauntlet.
---

# Implement a Malang module, spec-first

The order below is not bureaucracy. This project's whole thesis is that
contracts written before implementations are what make components swappable and
Phase 2 possible. Writing code first and reconciling later is how the contract
quietly becomes whatever the code happened to do.

## Step 1 — Gather the governing text (do not skip, do not summarise from memory)

Ask, or determine from the module path, which module this is. Then collect:

- every **FR** in `malang-phase1-spec.md` that names this module's behaviour
- the **contract** for it in spec §6.3 (speech modules) or §6.2 (router)
- its **flow** in design §5 (F-1..F-7)
- its **decisions** in design §4 (D-1..D-15)
- its **hazards** in `malang-phase1-hard-problems.md` (HP1..HP18)
- the **milestone exit test** it has to pass, from the build plan

Write these into a short `docs/modules/<name>.md` — requirement, contract,
hazards, exit test. This is the module's design note, and it is what a reviewer
(and you, in three weeks) reads instead of re-deriving.

## Step 2 — Contract test before implementation

Write the contract test from spec §6.3 first, against a fake implementation.
It must fail for the right reason. For speech modules this test is reused
verbatim against every future implementation — it is the thing that makes
"model choices are config, not architecture" true.

Delegate to **test-writer** if the test surface is large.

## Step 3 — Implement the smallest version that passes

- Pure core where the spec says pure (`route()`, reflex selector, endpoint
  fusion). Side effects at the edges.
- Config values from `malang.toml`, never constants in code (FR-13).
- Every probabilistic decision logs its ground truth and has a kill-switch.
  This is hard rule 5, and it applies to anything you are about to add that
  makes a guess.

## Step 4 — Wire the log

If the module produces anything that belongs in the record, add it to the
Scribe's schema **and** the validator **and** a fixture, in the same change.
A field that exists in code but not in the validator is a field Phase 2 cannot
trust. If this is a schema change, use the `schema-change` skill instead of
doing it here.

## Step 5 — The review gauntlet

Run in parallel, in one message:

- **spec-guardian** — is this the system the spec describes?
- **code-quality** — async, cancellation, resource lifetimes
- **security-review** — only if it touches credentials, egress, subprocesses,
  the status page, or the backup path
- **latency-auditor** — only if it sits on the hot path

Fix BLOCKING findings before moving on. Record DRIFT findings in the module's
design note even when you disagree — a disagreement you wrote down is evidence
later; one you argued away is nothing.

## Step 6 — Leave it usable

Build-plan hard rule 2: no milestone leaves the system broken overnight. If this
module is half-wired, put it behind a config flag that defaults to off, and say
so in the commit.
