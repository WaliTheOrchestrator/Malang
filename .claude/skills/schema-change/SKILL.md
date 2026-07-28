---
name: schema-change
description: Change the session log schema safely. Use for ANY change to session.jsonl, meta.json, the header event, event shapes, field names, or enum values. The log is the Phase 2 contract and the most expensive thing in the project to get wrong.
---

# Change the log schema

Spec C-7: *the logging schema is append-only and versioned; Phase 2 must never
require rewriting Phase 1 records.* Every conversation ever recorded is read
through this schema. A mistake here is not a bug you fix — it is a year of
memory you cannot fully trust.

## Before anything: is this actually necessary?

Adding a field is cheap now and expensive never. Removing or renaming one is
expensive forever. Ask which this is:

- **Additive** (new optional field, new event type, new enum value): fine,
  proceed.
- **Renaming or removing**: stop. Old records still contain the old shape and
  will forever. The correct move is to add the new field, leave the old one
  populated or null, and note the transition in the schema doc. There is no
  migration path, by design.

## The change, in one atomic step

All five, in the same commit — a schema change that lands in pieces produces
sessions that validate under no version at all:

1. `malang/scribe/schema.py` — the shape and the validator
2. `schema_version` bumped in the `header` event
3. `docs/schema/CHANGELOG.md` — version, date, what changed, why, and explicitly
   **how a Phase 2 reader should treat records written before this version**
4. Fixtures under `tests/fixtures/` regenerated, with at least one fixture kept
   at each older version so the reader stays backward-compatible
5. The reader/validator tested against every historical version, not just current

## Invariants that survive every change

- Line 1 is the `header` event, carrying `schema_version`, `config_hash`,
  `persona_version`. The version lives *inside* the file it versions, because
  `meta.json` is rebuilt from the JSONL after a crash.
- Every event carries a monotonic `seq`. Ordering authority is `seq`, never the
  wall clock.
- Append-only. Corrections are `amend` events. Nothing is ever rewritten.
- One `write()` per line, `flush()` + `os.fsync()` per event.
- The reader tolerates a torn final line and drops it.
- Malang turns carry `persona_version` and `responded_to`.
- `speaker` ∈ {waleed, malang, other, unknown}.

## Then verify against reality

Write one real session with the new code. Read it back with the validator. Run
the crash-recovery path against it. Confirm an *older* fixture still reads. Only
then tick anything.

## Finally

Ask spec-guardian to review the change against spec §6.1 specifically. This is
the one review that is never optional, because it is the one artifact the whole
project exists to produce.
