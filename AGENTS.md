# Agent Instructions — OpenJarvis

These instructions apply to **any** AI coding agent or assistant working in
this repository — Claude Code, Cursor, Codex, OpenCode, GitHub Copilot,
Gemini CLI, or anything else — not just one specific tool. This is the
project's tool-agnostic instruction file (the `AGENTS.md` convention).

## Language

All communication with the user in this repository — answers, questions,
explanations, progress updates — must be in Turkish. This is a standing
directive. (Code, commit messages, PR titles/descriptions, and technical
identifiers may stay in English; only user-facing text must be Turkish.)

## Skill discovery — check before free-handing a task

When the user asks a question, or brings a project / idea / request that
looks like more than a trivial one-off:

1. **Check local skills first.** Look at what this repo (and this agent's
   own built-in skill/plugin system, if it has one) already provides —
   `.claude/skills/**`, `.claude/skills/ecc/**`, etc.
2. **If nothing local fits well, search the open registry.** The Agent
   Skills ecosystem (the `agentskills.io` standard) indexes 88,000+ skills
   across every registry — the same catalog Nous Research's Hermes Agent
   surfaces at `hermes-agent.nousresearch.com/docs/skills`. Search it, e.g.
   with `npx skills find <keywords>` (see
   `.claude/skills/skill-discovery/SKILL.md` for the full tool reference).
3. **Present candidates, don't auto-install.** Tell the user what you
   found — local and/or online — and let them pick ("şu skill'i
   kullanalım" / "let's use this one") before proceeding with it.
4. **Never bulk-install from the registry.** One skill, fetched
   deliberately, reviewed for what its instructions/scripts actually do,
   then vendored — never a blind mass import. See
   `.claude/skills/skill-discovery/SKILL.md` and
   `.claude/rules/ecc/common/security.md`.

This directive holds regardless of which agent/tool is executing it.
