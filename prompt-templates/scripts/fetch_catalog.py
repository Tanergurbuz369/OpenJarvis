#!/usr/bin/env python3
"""Fetch the '2,500+ ChatGPT Prompt Templates' catalog from its public Notion site.

Source: https://ignacio-velasquez.notion.site/2-500-ChatGPT-Prompt-Templates-d9541e901b2b4e8f800e819bdc0256da
(curated by Ignacio Velásquez, free/public list).

Pulls every row of the prompt-templates database through Notion's public
`queryCollection` API. The API caps each response's recordMap at ~1000 blocks
while the database holds ~1945 rows, so the same view is queried under several
sort orders and the recordMaps are unioned to reach full coverage. Rows in the
"Jailbreak" category are kept but flagged `excluded` with their prompt text
stripped. Writes `catalog.json`.

Usage:
    python3 fetch_catalog.py [--out PATH]

No dependencies outside the standard library.
"""

import argparse
import json
import os
import ssl
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://ignacio-velasquez.notion.site/api/v3"
SPACE_ID = "60dcb895-9be7-418d-85ea-37835ad5cd95"
PROMPTS_COLLECTION = "9aa43529-272a-4add-8a33-60f37b444131"
PROMPTS_VIEW = "97fc38c5-3b00-45e0-aa1e-d6b804e6c7aa"
FOLDERS_COLLECTION = "f186cd86-f50c-4126-9c3a-418645e784d9"
FOLDERS_VIEW = "931596b3-60b2-4cc4-a43e-b1788a31407e"

# Prompt-collection schema property keys (stable Notion internal ids)
PROP_URL = "KCQ;"
PROP_TAG = "NR}z"
PROP_PLATFORM = "OziO"
PROP_CREATED = "PCQ{"
PROP_PROMPT = "Q]kQ"
PROP_DESCRIPTION = "[s^S"
PROP_AUTO_PROMPT = "^I>s"
PROP_FOLDER = "{`>D"

EXCLUDE_CATEGORIES = {"Jailbreak"}


def _opener():
    ca = os.environ.get("SSL_CERT_FILE") or "/etc/ssl/certs/ca-certificates.crt"
    ctx = ssl.create_default_context(cafile=ca if os.path.exists(ca) else None)
    handlers = []
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*handlers)


OPENER = _opener()


def post(endpoint, payload):
    req = urllib.request.Request(
        f"{BASE}/{endpoint}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    for attempt in range(4):
        try:
            with OPENER.open(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def load_page_block(block_id):
    """Fetch a single block via loadPageChunk (fallback for stragglers)."""
    data = post(
        "loadPageChunk",
        {
            "pageId": block_id,
            "limit": 50,
            "chunkNumber": 0,
            "verticalColumns": False,
            "cursor": {"stack": []},
        },
    )
    rec = data.get("recordMap", {}).get("block", {}).get(block_id)
    return unwrap(rec) if rec else None


def query_collection(coll_id, view_id, sort=None, limit=5000):
    loader = {
        "type": "reducer",
        "reducers": {"collection_group_results": {"type": "results", "limit": limit}},
        "searchQuery": "",
        "userTimeZone": "UTC",
    }
    if sort:
        loader["sort"] = sort
    return post(
        "queryCollection",
        {
            "source": {"type": "collection", "id": coll_id, "spaceId": SPACE_ID},
            "collectionView": {"id": view_id, "spaceId": SPACE_ID},
            "loader": loader,
        },
    )


def unwrap(record):
    v = record.get("value")
    if isinstance(v, dict) and "value" in v:
        v = v["value"]
    return v


def plain(prop):
    return "".join(
        seg[0]
        for seg in (prop or [])
        if isinstance(seg, list) and seg and isinstance(seg[0], str)
    ).strip()


def multiselect(prop):
    return sorted({t.strip() for t in plain(prop).split(",") if t.strip()})


def relation_ids(prop):
    ids = []
    for seg in prop or []:
        if isinstance(seg, list) and len(seg) > 1 and isinstance(seg[1], list):
            for mark in seg[1]:
                if isinstance(mark, list) and mark and mark[0] == "p":
                    ids.append(mark[1])
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parent.parent / "catalog.json")
    )
    args = ap.parse_args()

    folders_rm = query_collection(FOLDERS_COLLECTION, FOLDERS_VIEW)["recordMap"][
        "block"
    ]
    folder_names = {}
    for bid, rec in folders_rm.items():
        v = unwrap(rec)
        if v and v.get("type") == "page":
            folder_names[bid] = plain((v.get("properties") or {}).get("title"))

    # Union several sort orders to beat the ~1000-block recordMap cap.
    sorts = [
        None,
        [{"property": "title", "direction": "descending"}],
        [{"property": "title", "direction": "ascending"}],
        [{"property": PROP_CREATED, "direction": "ascending"}],
    ]
    blocks = {}
    block_ids = None
    for sort in sorts:
        data = query_collection(PROMPTS_COLLECTION, PROMPTS_VIEW, sort=sort)
        if block_ids is None:
            block_ids = data["result"]["reducerResults"]["collection_group_results"][
                "blockIds"
            ]
        for bid, rec in data["recordMap"].get("block", {}).items():
            if bid not in blocks:
                v = unwrap(rec)
                if v:
                    blocks[bid] = v
        if all(b in blocks for b in block_ids):
            break

    for bid in block_ids:
        if bid not in blocks:
            v = load_page_block(bid)
            if v:
                blocks[bid] = v

    missing = [b for b in block_ids if b not in blocks]
    if missing:
        print(f"warning: {len(missing)} rows could not be fetched")

    rows = []
    for bid in block_ids:
        v = blocks.get(bid)
        if not v:
            continue
        props = v.get("properties") or {}
        cats = sorted(
            {
                folder_names[f]
                for f in relation_ids(props.get(PROP_FOLDER))
                if folder_names.get(f)
            }
        )
        row = {
            "name": plain(props.get("title")),
            "description": plain(props.get(PROP_DESCRIPTION)),
            "prompt": plain(props.get(PROP_PROMPT)),
            "automatic_prompt": plain(props.get(PROP_AUTO_PROMPT)),
            "tags": multiselect(props.get(PROP_TAG)),
            "platform": multiselect(props.get(PROP_PLATFORM)),
            "url": plain(props.get(PROP_URL)),
            "categories": cats,
        }
        if set(cats) & EXCLUDE_CATEGORIES:
            row["prompt"] = ""
            row["automatic_prompt"] = ""
            row["excluded"] = "jailbreak — omitted for safety"
        rows.append(row)

    Path(args.out).write_text(
        json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    usable = sum(1 for r in rows if not r.get("excluded"))
    print(f"wrote {len(rows)} rows ({usable} usable) to {args.out}")
    print(
        "top categories:",
        Counter(c for r in rows for c in r["categories"]).most_common(10),
    )


if __name__ == "__main__":
    main()
