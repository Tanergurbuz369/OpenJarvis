# 1001+ AI Resources — Catalog

A structured, machine-readable extraction of Ignacio Velásquez's free
["1001+ AI Resources"](https://ignacio-velasquez.notion.site/1001-AI-Resources-30379fa273a740aa9e263a405d0f80f1)
Notion list: **1,109 unique AI tools, apps and sites** across ~70 categories
(assistants, text generation, image generation, chatbots, developer tools,
low-code/no-code, audio, productivity, …) — with every link liveness-checked.

| File | What it is |
|------|-----------|
| [`CATALOG.md`](CATALOG.md) | Human-readable catalog grouped by category, dead links flagged |
| [`catalog.json`](catalog.json) | The same data as structured JSON (`name`, `description`, `url`, `author`, `audience`, `categories`, `status`) |
| [`scripts/fetch_catalog.py`](scripts/fetch_catalog.py) | Regenerates `catalog.json` from the public Notion source (stdlib only) |

## What "working" means here

Unlike the [automation templates](../automation-templates/), these entries are
not installable workflows — they are **standalone AI products and websites**.
"Using" one simply means opening the link and signing up on that product's own
site. What this catalog guarantees is that the links are alive: the list dates
from the 2022–2023 AI wave and a meaningful share of those startups have since
shut down. Every one of the 1,109 URLs was checked (July 2026); pages that are
gone — 404s, dead domains, parked/for-sale domains, shutdown notices — are
flagged **[DEAD]** in the catalog and carry `"status": "dead"` in the JSON.

Every entry is currently classified live or dead. Sites behind aggressive bot
walls were checked page-by-page; where a check is ever inconclusive (e.g. after
a future re-run) the entry carries `"status": "unverified"` instead.

## How to use it

- Browse [`CATALOG.md`](CATALOG.md) by category; the table of contents is
  sorted by category size.
- Or query the JSON, e.g. all live image-generation tools:

```bash
python3 - <<'PY'
import json
rows = json.load(open("ai-resources/catalog.json"))
for r in rows:
    if r["status"] == "live" and "Image Generator" in r["categories"]:
        print(f"{r['name']}: {r['url']}")
PY
```

To refresh the catalog from the Notion source:

```bash
python3 ai-resources/scripts/fetch_catalog.py --check-links
```

## Credits & license

The resource list is curated by [Ignacio Velásquez](https://www.notion.com/@theveller)
and published free on his public Notion site. This directory only re-packages
the public index (names, links, descriptions) in a structured form with link
health data; the products themselves belong to their respective owners.
