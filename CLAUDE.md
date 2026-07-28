# Malang — project instructions

Personal AI companion. Phase 1 is **Presence**: summoned by voice, holds a
conversation, and writes a faithful local record. Solo, part-time, Windows,
CPU-only (Intel i3-1315U, 2P+4E, 8GB RAM with ~2GB reserved). Target: 4–6 months.

## Governing documents — read before non-trivial work

| File | Role |
|---|---|
| `malang-phase1-spec.md` | The contract. FRs, NFRs, constraints, §8 edge cases. **Wins all conflicts.** |
| `malang-phase1-design.md` | How. Modules, flows F-1..F-7, decisions D-1..D-15. |
| `malang-phase1-hard-problems.md` | HP1..HP18 — the failure modes, with names. |
| `malang-persona.md` | Who Malang is. System blocks 1–3. Versioned. |
| `malang-phase1-build-plan.md` | Current milestone and its exit test. |
| `docs/m0-measurements.md` | What the hardware actually said. Numbers not in here are assumptions. |

## Hard rules — these are not preferences

1. **M1 → M1.5 → M2.** Record, then presence, then voice. The backup exists
   before the first conversation does.
2. **Usable that evening.** No milestone leaves the system broken overnight.
   Half-finished work goes behind a default-off config flag.
3. **The Session Engine reads nothing from `memory/`.** One ≤100-token
   continuity string, handed in at session open, is the entire exception.
4. **One voice everywhere** — the P-6 Kokoro voice, including cues and reflex
   clips. Malang pronounces his own name correctly. Every speed gain passes an
   ear test.
5. **Every probabilistic component gets ground-truth logging and a kill-switch.**
   No exceptions.
6. **The API key lives in the environment or DPAPI.** Never in `malang.toml`,
   never in a tracked file. The status page never leaves `127.0.0.1`.
7. **Do not cut** M1, M1.5, or M6 under schedule pressure. Re-run the A-15
   probes on any model change.

## The record is sacred

`memory/` holds every conversation, forever, and is the entire point of the
project. Never write to `memory/raw/`. Tests use `tmp_path`. Chaos tests get
their own tree. The log schema (spec §6.1) is the Phase 2 contract: append-only,
`seq`-ordered, `fsync`'d per event, corrections as `amend` events, never
rewrites. Use the `schema-change` skill for any change to it.

## Conventions

- Python 3.12, `uv`, asyncio throughout; CPU-bound inference in thread executors.
- Config in `malang.toml` — no setting requires a code change (FR-13).
- Pure functions where the spec says pure: `route()`, the reflex selector, the
  endpoint fusion. They are specified that way so they can be tested offline.
- No test calls the Claude API. The echo brain (`--no-cloud`) exists for this.
- Prefer a ten-line script and a stopwatch over an argument about a number.

## Working style

Say what you actually measured, not what should happen. If a change relies on a
number that no measurement gate has produced, say so once and proceed. When a
gate rules against the plan, take the named reversal — they were pre-decided
cold so a bad number is a branch, not a crisis. Re-baseline in daylight.
