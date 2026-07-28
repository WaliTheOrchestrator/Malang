# Claude Code setup for Malang — what this is and how to install it

Drop-in configuration: 7 subagents, 5 skills, 6 hooks, 1 MCP server, and a
`CLAUDE.md`. Everything is tailored to this specific project — the hooks
enforce *your* hard rules, the reviewers read *your* spec.

## Install

```
# from the repo root
cp -r malang-claude-setup/.claude       .
cp    malang-claude-setup/CLAUDE.md     .
cp    malang-claude-setup/.mcp.json     .

git add .claude CLAUDE.md .mcp.json && git commit -m "Claude Code setup"
```

Then restart Claude Code once — the agent-directory watcher only covers
directories that existed at session start.

Verify:

```
/agents          # should list 7
/hooks           # should show SessionStart, PreToolUse, PostToolUse, Stop
/context         # confirm CLAUDE.md loaded
```

All six hooks were smoke-tested against a fixture tree before shipping: each
fires on its violation, and a clean file passes silently.

Requirements: `python` on PATH (the hooks are Python, so they behave identically
in PowerShell and Git Bash), Node 18+ for Context7.

---

## The hooks — your spec, enforced

These are the piece that matters most, because they work whether or not you
remember to invoke anything.

| Hook | Fires | Does |
|---|---|---|
| `session_brief.py` | SessionStart | 30-second cold-start brief: milestone, exit test, uncommitted work, whether M0 gates have run, last daily one-liner. Written for the day-8 return. |
| `secret_scan.py` | PreToolUse (Write/Edit/Bash) | **Denies** the write if it contains an API key or credential. Hard rule 6, enforced rather than reviewed. |
| `invariant_lint.py` | PostToolUse (Write/Edit) | The hard rules as regex. Session Engine touching `memory/`; Ear importing an STT; `scribe/writer.py` opening in write mode; a second TTS engine; allocation in the audio callback; a status page binding anything but loopback or exposing a mutating route. Exit 2 → Claude sees the violation and repairs it in the same turn. |
| `schema_check.py` | PostToolUse (Write/Edit) | Validates `.jsonl` fixtures against schema v1.3 and checks that `scribe/` modules know the whole field set — `seq`, `header`, `persona_version`, `responded_to`, `config_hash`, `amend`, `fsync`. |
| `persona_guard.py` | PostToolUse (Write/Edit) | Catches the three things that break together when Block 1 changes: stale `persona_version`, invalidated A-15 probe run, and **Block 1 falling under the fast tier's minimum cacheable prefix** — the failure that returns no error. |
| `invariant_lint.py --full` | Stop | Full-tree sweep at the end of every turn. Silent when clean. |
| `latency_regression.py` | *not wired yet* | Ships in the box, deliberately unwired. Add it to the `PostToolUse` array at **M3a**, when a hot path exists: blocks `time.sleep`, `print`, and blocking HTTP under `session/`, `speech/`, `ear/`, and flags cancellation logic with no `turn_id` (HP3). |

**Tuning them.** They will false-positive at first — that is expected, and the
right response is to narrow the regex, never to disable the hook. The rules live
in the `RULES` table at the top of `invariant_lint.py`, each citing the document
that created it. If a rule is genuinely wrong, change the **spec** first.

---

## The subagents

Invoke explicitly (`> use spec-guardian to review this`) or let Claude delegate.
Run reviewers **in parallel** — ask for all of them in one message.

| Agent | Model | Use it |
|---|---|---|
| `spec-guardian` | opus | Before every milestone close, and on anything touching the schema, state machine, router, or persona. Reports BLOCKING / **DRIFT** / NOTE — drift is the category nobody else is looking for. |
| `security-review` | opus | Milestone boundaries, credentials, egress, backup, status page. Has your real threat model, not a web-app checklist: stolen laptop first, key-in-repo second. |
| `code-quality` | sonnet | Async and realtime correctness — stale `turn_id`, swallowed `CancelledError`, allocation in the audio callback, ORT thread budgets, resource lifetimes on error paths. |
| `latency-auditor` | sonnet | From M3a. Checks measurement *honesty* as much as speed: edge-to-edge instrumentation, p95 not just p50, AC/DC split, minute-1 vs minute-10, core-class logging. |
| `chaos-engineer` | sonnet | Owns §8. Produces the coverage table, writes the automatable tests, writes numbered manual procedures for the ones that need real hardware. |
| `test-writer` | sonnet | Unit tests for the pure cores, contract tests per §6.3 interface, WAV-fixture pipeline harness. Never touches `memory/raw/`, never calls the API. |
| `docs-researcher` | sonnet | Before implementing against Pipecat, onnxruntime, sounddevice, `livekit.rtc.apm`, or the Anthropic SDK. Reports versions and hunts specifically for **silent** failure modes. |

---

## The skills

Invoke as `/new-module`, `/measure`, etc.

| Skill | For |
|---|---|
| `/new-module` | Spec-first module implementation: gather FRs → contract test → implement → review gauntlet → leave it usable. |
| `/measure` | Run a P-gate honestly. Script first, real machine, percentiles, conditions recorded, ruling written down with what would reverse it. |
| `/probe-runner` | A-15 character probes with the de-biased grading discipline (shuffle, month's delay, second grader). |
| `/milestone-close` | Exit test → parallel gauntlet → invariant sweep → build-plan tick → commit → "is it usable tonight?" |
| `/schema-change` | Any change to the log. Additive vs. destructive, five artifacts in one commit, backward-compat test against old fixtures. |

Also built in: `/code-review` for a general pass, and `/verify` — worth knowing
they exist so you don't rebuild them.

---

## MCP

Only one is worth it. Most of this project is local Python, local models, and a
mic in your room — there is very little for an MCP to reach.

- **Context7** (`.mcp.json`, already configured) — versioned library docs. Pays
  for itself the first time it stops Claude inventing a Pipecat ≥1.0 signature.
- **GitHub MCP** — add later, only if you start working through issues and PRs.
  `claude mcp add --transport http github https://api.githubcopilot.com/mcp/`
- Skip the rest. An MCP you don't need is context you pay for every turn.

---

## Two things worth knowing early

**Plan mode before big changes.** `Shift+Tab` twice. On a project this
spec-heavy, having Claude produce a plan you approve before it edits ten files
is worth more than any subagent here.

**`/context` when things get strange.** Long sessions drift. If answers start
ignoring the spec, check what's actually loaded before assuming the model got
worse.

---

## Deliberately not included

- **A pre-commit hook running the full test suite.** Your sessions are short and
  bursty; a 40-second gate on every commit will get bypassed within a week, and
  a bypassed gate is worse than none. The Stop hook does the cheap sweep;
  `/milestone-close` does the expensive one, when it's worth it.
- **A test-runner subagent.** `pytest -q` in Bash is faster and clearer than
  delegating. Subagents earn their cost on *judgment*, not on running commands.
- **An auto-formatter hook.** Add `ruff format` when the codebase exists. On day
  one it just makes diffs noisy.
