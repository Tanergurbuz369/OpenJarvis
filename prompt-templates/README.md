# ChatGPT Prompt Templates — for Claude Code & agents

A structured, searchable library of reusable prompt templates, wired up so
**Claude Code and OpenJarvis agents can actually use it** — not just read it.
Two collections, one shared interface:

- **English (1,941 prompts)** — from Ignacio Velásquez's free
  ["2,500+ ChatGPT Prompt Templates"](https://ignacio-velasquez.notion.site/2-500-ChatGPT-Prompt-Templates-d9541e901b2b4e8f800e819bdc0256da)
  Notion list; many carry an *expanded expert* variant.
- **Turkish (895 prompts)** — from the *"ChatGPT'yi maximumda kullanın"* PDF,
  across 20 professional categories (Pazarlama, Satış, İK, Mühendisler, …).

| File | What it is |
|------|-----------|
| [`catalog.json`](catalog.json) | English entries (`name`, `description`, `prompt`, `automatic_prompt`, `tags`, `platform`, `categories`, `url`) |
| [`catalog.tr.json`](catalog.tr.json) | Turkish entries (same schema, `lang: "tr"`) |
| [`prompts/`](prompts/) · [`prompts-tr/`](prompts-tr/) | Human-readable Markdown, one file per category |
| [`CATALOG.md`](CATALOG.md) · [`CATALOG.tr.md`](CATALOG.tr.md) | Category indexes |
| [`scripts/prompt.py`](scripts/prompt.py) | Search / show / fill CLI (`--lang en\|tr\|all`) — the tool agents call |
| [`scripts/fetch_catalog.py`](scripts/fetch_catalog.py) | Regenerates `catalog.json` from the Notion source (stdlib only) |

The CLI auto-loads every `catalog*.json` in this directory, so both languages
are searchable through one command. Each template has a short **prompt** and
sometimes an **expanded prompt** (a fuller expert version). Placeholders in
`[brackets]` are fill-ins; `[PROMPT]` = your topic, `[TARGETLANGUAGE]` = output
language.

## Set up for Claude Code

The Claude Code skill lives at
[`claude-code-skill/SKILL.md`](claude-code-skill/SKILL.md). Activate it by
copying it into a skills folder Claude Code loads — either this repo's
`.claude/skills/` (repo-local) or your `~/.claude/skills/` (available
everywhere):

```bash
# repo-local (this project only)
mkdir -p .claude/skills/prompt-templates
cp prompt-templates/claude-code-skill/SKILL.md .claude/skills/prompt-templates/

# or global (all your projects)
mkdir -p ~/.claude/skills/prompt-templates
cp prompt-templates/claude-code-skill/SKILL.md ~/.claude/skills/prompt-templates/
```

(The repo keeps `.claude/` git-ignored, so the skill is shipped here as a
tracked file and copied in during setup.) Once installed, just ask naturally:

> "Give me a prompt for a cold outreach email to dentists."
> "Find a LinkedIn post prompt about breaking down a complex topic."

Claude searches this library, picks the best template, and fills in the
placeholders.

## Set up for OpenJarvis agents

The bundled OpenJarvis skill
[`src/openjarvis/skills/data/prompt-template-find.toml`](../src/openjarvis/skills/data/prompt-template-find.toml)
chains `shell_exec` + `think` to search the library, pick a match, and fill it
in. Any agent with the `shell_exec` tool can invoke it:

```bash
jarvis ask "use the prompt-template-find skill to get me a prompt for a product launch tweet"
```

## Use the CLI directly (any agent, any language)

The CLI is the reliable interface — stdlib Python, no dependencies, stable
`--json` output for programmatic callers:

```bash
# Rank templates by a query (both languages by default)
python3 prompt-templates/scripts/prompt.py search "cover letter" --limit 5

# Restrict to one language
python3 prompt-templates/scripts/prompt.py search "pazarlama stratejisi" --lang tr
python3 prompt-templates/scripts/prompt.py categories --lang tr

# Print a template by id or name (--expanded = the expert variant)
python3 prompt-templates/scripts/prompt.py show "AIDA Copywriting" --expanded

# Fill placeholders and print ready-to-paste text
python3 prompt-templates/scripts/prompt.py fill "Cold Email" \
    -s PROMPT="a CRM for dentists" -s TARGETLANGUAGE="English"

# Structured output for scripting
python3 prompt-templates/scripts/prompt.py search "blog intro" --json
```

## Notes

- Templates were written for ChatGPT but work with any capable LLM, including
  Claude. The "Ignore all previous instructions" opener some expanded prompts
  carry is persona-setting boilerplate — keep or trim it.
- **Excluded:** the source list's "Jailbreak" category (4 DAN/AIM-style
  guardrail-bypass prompts) was deliberately left out. Those rows stay in
  `catalog.json` flagged `"excluded"` with empty prompt text, and the CLI
  refuses to print them.
- Counts (English): 1,941 usable templates across 45 categories; 1,631 carry
  inline prompt text, the rest are external GPT/tool links (`url`).
- Counts (Turkish): 895 prompts across 20 professional categories. The source
  PDF's **Satış** section is truncated at item 14, and a few sections are
  missing their first entries in the export — `catalog.tr.json` / `CATALOG.tr.md`
  reflect what is actually present, not the headline counts.

## Credits & license

The English prompt list is curated by [Ignacio Velásquez](https://www.notion.com/@theveller)
and published free on his public Notion site. The Turkish set is extracted from
the *"ChatGPT'yi maximumda kullanın"* community PDF. This directory re-packages
those indexes (names, prompts, descriptions) in a structured, agent-usable form;
the prompts themselves belong to their respective authors.
