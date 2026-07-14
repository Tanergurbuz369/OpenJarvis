---
name: prompt-templates
description: >-
  Find and reuse a ready-made prompt from the bundled library of 2,800+ prompt
  templates — English (marketing, business, copywriting, coding, education,
  frameworks like AIDA/PAS, expert personas) and Turkish (Pazarlama, Satış, İK,
  Mühendisler, Avukatlar, and 15 more professional categories). Use this
  whenever the user asks for "a prompt for X" / "X için prompt", wants a starting
  prompt, a copywriting framework, a cold email/DM, a persona prompt, or
  otherwise needs a proven template instead of writing one from scratch.
---

# Prompt Templates

A local, searchable library of 2,800+ reusable ChatGPT/LLM prompt templates
(English + Turkish) lives in `prompt-templates/`. Each entry has a short prompt
and often an "expanded" expert version (a fuller prompt that sets an expert
persona and detailed instructions). Prefer this library over inventing a prompt when the
user wants a template.

## How to use it

Shell out to the CLI — it needs only Python 3, no dependencies:

```bash
# Rank templates by a query (add --limit N; --json for structured output)
python3 prompt-templates/scripts/prompt.py search "cold email"

# Both languages are searched by default; filter with --lang en|tr
python3 prompt-templates/scripts/prompt.py search "pazarlama stratejisi" --lang tr

# List categories and counts (optionally per language)
python3 prompt-templates/scripts/prompt.py categories --lang tr

# Print a template's text by id or name (--expanded for the expert variant)
python3 prompt-templates/scripts/prompt.py show 191
python3 prompt-templates/scripts/prompt.py show "AIDA Copywriting" --expanded

# Print a template with placeholders filled in
python3 prompt-templates/scripts/prompt.py fill "Cold Email" \
    -s PROMPT="a CRM for dentists" -s TARGETLANGUAGE="English"
```

Match the language to the user: a Turkish request ("... için prompt") should be
answered from the Turkish set (`--lang tr`), an English one from the English
set. Typical flow: `search` for the user's need → `show` the top hit (usually
`--expanded` for English) → substitute placeholders like `[product/service]` /
`[ürün/hizmet]`, `[PROMPT]` (the user's topic), `[TARGETLANGUAGE]` (output
language) with `fill` or by editing inline → hand the finished prompt to the
user or run it yourself.

You can also browse the human-readable files in `prompt-templates/prompts/` and
`prompt-templates/prompts-tr/` (one Markdown file per category) or query the
`catalog*.json` files directly.

## Notes

- Templates were written for ChatGPT but work with any capable LLM, including
  Claude. The "Ignore all previous instructions" opener some expanded prompts
  carry is just persona-setting boilerplate — safe to keep or trim.
- The source list's "Jailbreak" category (DAN/AIM-style guardrail-bypass
  prompts) was deliberately excluded; those entries remain in `catalog.json`
  flagged `"excluded"` with no prompt text, and the CLI refuses to print them.
- Sources: English set — [2,500+ ChatGPT Prompt Templates](https://ignacio-velasquez.notion.site/2-500-ChatGPT-Prompt-Templates-d9541e901b2b4e8f800e819bdc0256da)
  by Ignacio Velásquez (free public list); Turkish set (895 prompts, 20
  professional categories) — the *"ChatGPT'yi maximumda kullanın"* community PDF.
