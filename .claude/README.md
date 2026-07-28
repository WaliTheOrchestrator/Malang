# .claude

Project-level configuration for [Claude Code](https://docs.claude.com/en/docs/claude-code).

## Layout

| Path            | Purpose                                                                 |
| --------------- | ---------------------------------------------------------------------- |
| `settings.json` | Shared, version-controlled settings (permissions, env, hooks).         |
| `settings.local.json` | Personal, machine-local overrides. Git-ignored.                 |
| `commands/`     | Custom slash commands (`/name`), one Markdown file each.               |
| `agents/`       | Custom subagent definitions (Markdown with frontmatter).              |
| `skills/`       | Project skills, each in its own folder with a `SKILL.md`.             |
| `hooks/`        | Scripts invoked by hooks configured in `settings.json`.                |

## Notes

- `settings.json` is committed and shared with the team.
- `settings.local.json` is for your personal overrides and is git-ignored.
- See the docs for the full settings schema and hook events.
