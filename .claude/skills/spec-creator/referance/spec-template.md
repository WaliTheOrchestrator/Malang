# <ID> — <Title>

**Milestone:** <M-n> · **Branch:** `feat/<slug>` · **Created:** <date>
**Spec version:** 1.0 · **Status:** draft | approved | building | done
**Governing docs:** malang-phase1-spec.md §<x>, design §<y>, HP<n>

---

## 1. Overview

Three to six sentences. What this feature *is*, and — more importantly — what
it makes possible that is impossible without it. If you cannot say why the
project is worse off without this, do not build it yet.

## 2. Governing requirements

Quote them; do not paraphrase. Every line here is a thing the reviewer will
check the code against.

| Source | Requirement (quoted) |
|---|---|
| FR-n | "..." |
| C-n | "..." |
| D-n | "..." |
| HP-n | the hazard, and the mitigation the spec already committed to |

## 3. Depends on

- **Specs / milestones:** what must exist first, and why.
- **Measurement gates:** which of P-1..P-6 must have *ruled* before this is
  trustworthy. If a gate this depends on has not run, say so in bold — the
  feature can still be built, but its numbers are assumptions.
- **Hardware / environment:** mic, speakers, network, battery state.

## 4. Contracts

The event interface this honours or defines, in spec §6.3 shape. Omit if the
feature touches no module boundary.

```
Component:  method(args) -> events: {...}
```

State whether this is a **new** contract (goes into §6.3, so future
implementations are swappable) or an **existing** one being implemented.

## 5. Log schema impact

One of:

- **None** — writes nothing to the record.
- **Additive** — new optional field or event type. List them. Requires the
  `schema-change` skill.
- **Breaking** — stop. Spec C-7 says Phase 2 must never require rewriting
  Phase 1 records. Redesign as additive.

## 6. Latency and resource budget

Omit if off the hot path. Otherwise: which §5 stages this touches, the budget
it must stay inside (p50 and p95), and its share of the thread and RAM budget
on the i3-1315U.

## 7. Config keys

FR-13: no setting requires a code change. Every knob this introduces, with its
default, its range, and — for anything probabilistic — its **kill-switch**.

```toml
[section]
key = default   # what it does; kill-switch: <how to turn the behaviour off>
```

## 8. Routes

**Omit this section entirely unless the feature adds an HTTP route.** In this
project that means the M6.5 status page and nothing else. If present: method,
path, response shape, and a restatement that it is read-only and bound to
127.0.0.1.

## 9. Files to create

| Path | Purpose |
|---|---|

## 10. Files to change

| Path | Change | Risk |
|---|---|---|

## 11. New dependencies

| Package | Version | Why | CPU-only? | Windows? | License |
|---|---|---|---|---|---|

If the answer to "CPU-only" or "Windows" is *unknown*, that is a research task
for `docs-researcher` before this spec is approved — not a discovery for
implementation day.

## 12. Rules for implementation

Start with the hard rules that actually bite this feature (not all seven —
only the ones in play), then the feature-specific rules.

1. ...
2. ...

## 13. Failure modes

New or touched rows of spec §8. Each one is a case `chaos-engineer` will have
to turn into a named test.

| Case | Behaviour |
|---|---|

## 14. Test plan

- **Unit:** pure functions, table-driven.
- **Contract:** the §6.3 interface test, run against the real implementation
  and the fake.
- **Pipeline harness:** WAV fixtures through the real graph, if audio is involved.
- **Manual:** the parts that need the real machine — numbered, with the expected
  observation written down.

No test writes under `memory/raw/`. No test calls the Claude API.

## 15. Definition of done

Every box, ticked, with evidence:

- [ ] Milestone exit test passes — quote it, and state the number observed
- [ ] `python .claude/hooks/invariant_lint.py --full` clean
- [ ] `pytest -q` green
- [ ] A session written by this code validates against the schema
- [ ] `spec-guardian` and `code-quality` run; BLOCKING findings resolved
- [ ] `security-review` if credentials / egress / subprocess / backup touched
- [ ] `latency-auditor` if on the hot path
- [ ] Any measurement gate this used has its ruling in `docs/m0-measurements.md`
- [ ] Config keys documented in `malang.toml` with defaults
- [ ] **Usable that evening** — nothing left broken overnight
- [ ] Build-plan checkbox ticked; milestone note written

## 16. Out of scope

What this deliberately does not do, and which phase or milestone owns it.
The line that matters most here: anything that reads from `memory/`.