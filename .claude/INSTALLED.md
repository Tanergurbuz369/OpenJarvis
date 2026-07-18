# claude-code-best-practice toolkit

Installed from https://github.com/shanraisshan/claude-code-best-practice
Source commit: `a151b3784061929b327ae5f9012376dc68fc58d6`

## What this adds
- `settings.json` — permissions, hooks wiring, spinner/status customizations, env (`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80`), `plansDirectory: ./reports`
- `hooks/` — single `scripts/hooks.py` router wired to every Claude Code hook event (plays sounds from `hooks/sounds/`, stdlib-only)
- `agents/`, `commands/`, `skills/`, `rules/` — full toolkit incl. demo flows (weather-orchestrator, time, presentation)
- `../.mcp.json` — playwright, context7, deepwiki MCP servers

## Try it
Run `/weather-orchestrator` to see a full command -> agent -> skill flow.

Note: this repo's root `.gitignore` normally excludes `.claude/`; it was force-added here so the toolkit is versioned. `best-practice-CLAUDE.md` is the source repo's CLAUDE.md kept for reference (not auto-loaded).
