# 365+ Automation Templates — Catalog & Setup Guide

A structured, machine-readable extraction of Ignacio Velásquez's free
["365+ Automation Templates"](https://ignacio-velasquez.notion.site/365-Automation-Templates-245087908e5447c2a1a2c66d8c90019c)
Notion list: **377 entries** (319 ready-made templates, 44 automation apps, a few ideas)
across Make, Bardeen, Zapier, IFTTT, Whalesync, Pabbly Connect and Integrately —
with every link liveness-checked.

| File | What it is |
|------|-----------|
| [`CATALOG.md`](CATALOG.md) | Human-readable catalog, grouped by platform and category, dead links flagged |
| [`catalog.json`](catalog.json) | The same data as structured JSON (`name`, `description`, `url`, `tag`, `categories`, `platform`, `status`) |
| [`scripts/fetch_catalog.py`](scripts/fetch_catalog.py) | Regenerates `catalog.json` from the public Notion source (stdlib only) |

## Important: what "installing" these templates means

These templates run **on their own SaaS platforms**, not inside this repository.
Each one is activated by opening its link **while logged into your own account**
on that platform and connecting your own app credentials (Google, Slack, etc.).
Nobody can pre-install them for you — every template needs *your* OAuth
authorizations to run against *your* accounts.

The one-time setup per platform:

### Make (229 templates — the majority)
1. Create a free account at [make.com](https://www.make.com/en/register) (free tier: 1,000 ops/month).
2. Open any Make template link from the catalog → click **"Use this template"** (or "Get more details" → create scenario).
3. Make walks you through connecting each app the scenario uses (e.g. Google Sheets, Gmail). Each connection is a one-time OAuth consent; connections are reused by later templates.
4. Review the scenario, click **Run once** to test, then toggle **Scheduling ON** to activate.

### Bardeen (78 templates)
Bardeen is a **Chrome extension** — install it from the [Chrome Web Store](https://chromewebstore.google.com/detail/bardeen-automate-browser/ihhkmalpkhkoedlmcnilbbhhbhnicjga), create an account, then open any Bardeen "playbook" link from the catalog and click **"Try it"**. Playbooks run locally in your browser; app integrations (Notion, Google Sheets, …) are connected once from the extension's sidebar.

### Zapier (30 templates)
1. Create an account at [zapier.com](https://zapier.com/sign-up) (free tier: 100 tasks/month).
2. Open a Zapier template link → **"Try this Zap"** → connect the two apps → turn the Zap on.

### IFTTT (24 templates)
1. Create an account at [ifttt.com](https://ifttt.com/join) (free tier: a few applets).
2. Open an applet link → **"Connect"** → authorize the services → done.

### Whalesync / Pabbly Connect / Integrately (16 entries)
These entries are mostly **apps/two-way sync products**, not one-click templates.
Open the link, sign up, and follow the product's own onboarding
(e.g. Whalesync template packs sync Webflow/Notion/Airtable bases).

## Recommended order (if you're starting from zero)

1. Create the Make account first — 229 of the 319 templates (~72%) run there.
2. Skim [`CATALOG.md`](CATALOG.md) by category (CRM, Marketing, Productivity, …) and shortlist the 5–10 automations you actually need. Free-tier op limits make "activate everything" both impossible and pointless — activate what you'll use.
3. Connect your core apps once (Google Workspace, Slack, Notion, …); every later template reuses those connections.
4. Add Bardeen's extension for the browser-scraping playbooks.

## Link status

All 377 links were checked (July 2026). Entries whose pages have been taken
down by the platform (removed Twitter/X integrations, discontinued apps, …)
are flagged **[DEAD]** in the catalog and carry `"status": "dead"` in the JSON —
don't waste time on those.

To re-verify or refresh the catalog:

```bash
python3 automation-templates/scripts/fetch_catalog.py --check-links
```

Note that Make.com's bot protection answers plain HTTP clients with 403; a 403
there means "unverified", not "dead".

## Credits & license

The template list is curated by [Ignacio Velásquez](https://www.notion.com/@theveller)
and published free on his public Notion site. This directory only re-packages
the public index (names, links, descriptions) in a structured form with link
health data; the templates themselves belong to their respective platforms.
