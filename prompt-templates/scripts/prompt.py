#!/usr/bin/env python3
"""Search and render the ChatGPT prompt-template library.

The library (`prompt-templates/catalog.json`) holds 1,900+ reusable prompt
templates extracted from Ignacio Velásquez's free "2,500+ ChatGPT Prompt
Templates" Notion list. This CLI lets a human — or an agent shelling out — find
a template and print it ready to paste into Claude, ChatGPT, or any LLM.

Examples:
    python3 prompt.py search "cold email"          # rank templates by query
    python3 prompt.py search cover letter --limit 5
    python3 prompt.py categories                    # list categories + counts
    python3 prompt.py show "AIDA Copywriting"       # print a template by name
    python3 prompt.py show 42 --expanded            # print the expanded variant
    python3 prompt.py fill "Cold Email" -s PROMPT="a CRM for dentists"

`--json` on any command prints machine-readable output for programmatic use.
No dependencies outside the standard library.
"""

import argparse
import json
import re
import sys
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent


def load():
    # Merge the English catalog and any language catalogs (catalog.<lang>.json).
    rows = []
    for path in sorted(CATALOG_DIR.glob("catalog*.json")):
        stem = path.name[len("catalog") : -len(".json")].strip(".")
        lang = stem or "en"
        for r in json.loads(path.read_text(encoding="utf-8")):
            r.setdefault("lang", lang)
            rows.append(r)
    for i, r in enumerate(rows):
        r["_id"] = i
    return rows


def by_lang(rows, lang):
    if not lang or lang == "all":
        return rows
    return [r for r in rows if r.get("lang", "en") == lang]


def usable(r):
    return bool(r.get("prompt") or r.get("automatic_prompt")) and not r.get("excluded")


def score(row, terms):
    name = row["name"].lower()
    desc = (row.get("description") or "").lower()
    cats = " ".join(row.get("categories") or []).lower()
    tags = " ".join(row.get("tags") or []).lower()
    body = (row.get("prompt", "") + " " + row.get("automatic_prompt", "")).lower()
    s = 0
    for t in terms:
        if t in name:
            s += 10
        if t in cats or t in tags:
            s += 4
        if t in desc:
            s += 3
        if t in body:
            s += 1
    if " ".join(terms) in name:
        s += 15
    return s


def best_prompt(row, expanded):
    if expanded:
        return row.get("automatic_prompt") or row.get("prompt") or ""
    return row.get("prompt") or row.get("automatic_prompt") or ""


def cmd_search(rows, args):
    rows = by_lang(rows, getattr(args, "lang", None))
    terms = [t.lower() for t in re.split(r"\s+", args.query.strip()) if t]
    ranked = sorted(
        ((score(r, terms), r) for r in rows if usable(r)),
        key=lambda x: (-x[0], x[1]["name"].lower()),
    )
    hits = [(s, r) for s, r in ranked if s > 0][: args.limit]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": r["_id"],
                        "name": r["name"],
                        "score": s,
                        "categories": r["categories"],
                    }
                    for s, r in hits
                ],
                indent=1,
            )
        )
        return
    if not hits:
        print(f"No templates matched {args.query!r}.")
        return
    for s, r in hits:
        cats = ", ".join(r["categories"]) or "—"
        print(f"[{r['_id']}] {r['name']}  ({cats})")
        if r.get("description"):
            print("    " + r["description"][:140])


def cmd_categories(rows, args):
    from collections import Counter

    rows = by_lang(rows, getattr(args, "lang", None))
    c = Counter(
        cat for r in rows if usable(r) for cat in (r["categories"] or ["Uncategorized"])
    )
    if args.json:
        print(json.dumps(dict(c.most_common()), indent=1))
        return
    for cat, n in c.most_common():
        print(f"{n:>4}  {cat}")


def resolve(rows, ref):
    if ref.isdigit():
        i = int(ref)
        return next((r for r in rows if r["_id"] == i), None)
    low = ref.lower()
    exact = [r for r in rows if r["name"].lower() == low]
    if exact:
        return exact[0]
    part = [r for r in rows if low in r["name"].lower() and usable(r)]
    return part[0] if part else None


def cmd_show(rows, args):
    r = resolve(rows, args.ref)
    if not r:
        print(f"No template found for {args.ref!r}.", file=sys.stderr)
        sys.exit(1)
    if r.get("excluded"):
        print(f"[{r['_id']}] {r['name']} — {r['excluded']}", file=sys.stderr)
        sys.exit(2)
    text = best_prompt(r, args.expanded)
    if args.json:
        print(
            json.dumps(
                {
                    "id": r["_id"],
                    "name": r["name"],
                    "description": r.get("description"),
                    "categories": r["categories"],
                    "tags": r.get("tags"),
                    "prompt": text,
                },
                indent=1,
                ensure_ascii=False,
            )
        )
        return
    print(text)


def cmd_fill(rows, args):
    r = resolve(rows, args.ref)
    if not r or r.get("excluded"):
        print(f"No usable template for {args.ref!r}.", file=sys.stderr)
        sys.exit(1)
    text = best_prompt(r, args.expanded)
    for sub in args.set or []:
        if "=" not in sub:
            print(f"--set expects KEY=VALUE, got {sub!r}", file=sys.stderr)
            sys.exit(1)
        key, value = sub.split("=", 1)
        for token in (f"[{key}]", f"[{key.upper()}]", f"[{key.lower()}]"):
            text = text.replace(token, value)
    print(text)


def main():
    rows = load()
    ap = argparse.ArgumentParser(
        description="Search the ChatGPT prompt-template library."
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # --json is accepted both before and after the subcommand.
    def with_json(parser):
        # SUPPRESS so an absent subcommand --json doesn't clobber a top-level one.
        parser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help="machine-readable output",
        )
        return parser

    s = with_json(sub.add_parser("search", help="rank templates by a query"))
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--lang", help="filter by language: en, tr, all (default all)")
    s.set_defaults(func=cmd_search)

    c = with_json(sub.add_parser("categories", help="list categories and counts"))
    c.add_argument("--lang", help="filter by language: en, tr, all (default all)")
    c.set_defaults(func=cmd_categories)

    sh = with_json(sub.add_parser("show", help="print a template by id or name"))
    sh.add_argument("ref")
    sh.add_argument(
        "--expanded", action="store_true", help="prefer the expanded expert variant"
    )
    sh.set_defaults(func=cmd_show)

    fl = with_json(
        sub.add_parser("fill", help="print a template with placeholders substituted")
    )
    fl.add_argument("ref")
    fl.add_argument("-s", "--set", action="append", metavar="KEY=VALUE")
    fl.add_argument("--expanded", action="store_true")
    fl.set_defaults(func=cmd_fill)

    args = ap.parse_args()
    args.func(rows, args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Downstream closed the pipe early (e.g. `| head`); exit quietly.
        try:
            sys.stdout.close()
        except Exception:
            pass
