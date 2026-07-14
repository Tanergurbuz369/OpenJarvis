# Iterative Loop — Usage Log

This repo's `.gitignore` deliberately excludes `CLAUDE.md` and `.claude/`
("Claude Code project instructions (per-developer)"), so no Claude Code
config is committed here. This file exists instead, as the durable,
version-controlled record of how the `iterative-loop` skill applies to
this project.

`iterative-loop` runs a self-scoring PLAN → DO → VERIFY → DECIDE loop
until every success criterion scores 8/10 or higher, deriving the task
and criteria from context instead of requiring them to be spelled out by
hand. It becomes available in any Claude Code session on this repo once
installed globally (`~/.claude/skills/iterative-loop/`) — see the
canonical source, template library, and `install-global.sh` at
[`_Agent-Projects/frameworks/iterative-loop/`](https://github.com/Tanergurbuz369/_Agent-Projects/tree/master/frameworks/iterative-loop).
It is personal agent tooling, not a project policy.

## History

| Date | Task | Final scores | Note |
|---|---|---|---|
| 2026-07-14 | Bootstrap: document the iterative-loop skill's applicability to this repo | Scope:9, Respects repo conventions:9, Discoverability:8 | `.claude/CLAUDE.md` were intentionally NOT committed (see gitignore); this log is the repo-tracked pointer instead |

## Where it can be used in this project

- Feature development loops (e.g. agent primitives, evaluation harnesses)
- Bug fix loops with regression-test criteria
- Documentation passes (`docs/`, `mkdocs.yml`-driven site)
