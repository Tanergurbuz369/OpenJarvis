# YouMind OpenLab

Skills vendored from the [YouMind OpenLab](https://github.com/YouMind-OpenLab) GitHub organization
(https://youmind.com). Each subdirectory mirrors an upstream skill repo's `SKILL.md` and support
files verbatim so Claude Code can load it directly from this repo.

## Skills

- **nano-banana-pro-prompts-recommend-skill** — recommends AI image generation prompts from
  YouMind's 10,000+ curated Nano Banana Pro (Gemini) prompt library, with sample images.
  Source: https://github.com/YouMind-OpenLab/nano-banana-pro-prompts-recommend-skill

## Keeping in sync

These skills auto-update their own data at runtime (see each skill's `SKILL.md` "Setup" section —
typically `node scripts/setup.js --check`). The prompt data itself (`references/*.json`) is not
committed to this repo; it's downloaded on demand and gitignored, matching upstream's own
distribution model (code vs. 30MB+ of data are split).

To pull in SKILL.md/code updates from upstream, re-fetch the files listed above and diff against
what's here.
