#!/usr/bin/env python3
"""Fetch the '1001+ AI Resources' catalog from its public Notion site.

Source: https://ignacio-velasquez.notion.site/1001-AI-Resources-30379fa273a740aa9e263a405d0f80f1
(curated by Ignacio Velásquez, free/public list).

Pulls every row of the "AI Resources" database through Notion's public
`queryCollection` API. The API caps each response's recordMap at ~1000
blocks while the database holds 1100+, so the same view is queried under
three different sort orders and the recordMaps are unioned to reach full
coverage. Optionally checks link liveness and writes `catalog.json`.

Usage:
    python3 fetch_catalog.py [--check-links] [--out PATH]

No dependencies outside the standard library.
"""

import argparse
import concurrent.futures
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://ignacio-velasquez.notion.site/api/v3"
SPACE_ID = "60dcb895-9be7-418d-85ea-37835ad5cd95"
RESOURCES_COLLECTION = "535361ae-3468-49d0-8f52-177034c586ce"
RESOURCES_VIEW = "62c0ec71-4688-4157-bf2f-6f7fd0478932"
FOLDERS_COLLECTION = "194f4987-f6f8-4b41-95c4-287d6d925012"
FOLDERS_VIEW = "4095bb58-5b35-4c5b-ad8f-af76226c337e"

# Resources-collection schema property keys (stable Notion internal ids)
PROP_DESCRIPTION = ":RNw"
PROP_FOLDER = "=?dV"
PROP_AUTHOR = "E}mi"
PROP_AUDIENCE = "OMpW"
PROP_CREATED = "U>X^"
PROP_URL = "cypw"


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


def query_collection(coll_id, view_id, sort=None):
    loader = {
        "type": "reducer",
        "reducers": {"collection_group_results": {"type": "results", "limit": 2000}},
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


def relation_ids(prop):
    ids = []
    for seg in prop or []:
        if isinstance(seg, list) and len(seg) > 1 and isinstance(seg[1], list):
            for mark in seg[1]:
                if isinstance(mark, list) and mark and mark[0] == "p":
                    ids.append(mark[1])
    return ids


def check_link(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}, method="GET"
    )
    try:
        with OPENER.open(req, timeout=25) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-links", action="store_true")
    ap.add_argument(
        "--out", default=str(Path(__file__).resolve().parent.parent / "catalog.json")
    )
    args = ap.parse_args()

    folders_rm = query_collection(FOLDERS_COLLECTION, FOLDERS_VIEW)["recordMap"]["block"]
    folder_names = {}
    for bid, rec in folders_rm.items():
        v = unwrap(rec)
        if v and v.get("type") == "page":
            folder_names[bid] = plain((v.get("properties") or {}).get("title"))

    # Union three sort orders to beat the ~1000-block recordMap cap.
    sorts = [
        None,
        [{"property": "title", "direction": "descending"}],
        [{"property": PROP_CREATED, "direction": "ascending"}],
    ]
    blocks = {}
    block_ids = None
    for sort in sorts:
        data = query_collection(RESOURCES_COLLECTION, RESOURCES_VIEW, sort=sort)
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

    missing = [b for b in block_ids if b not in blocks]
    if missing:
        print(f"warning: {len(missing)} rows not returned by any sort order")

    rows, seen = [], set()
    for bid in block_ids:
        v = blocks.get(bid)
        if not v:
            continue
        props = v.get("properties") or {}
        name = plain(props.get("title"))
        url = plain(props.get(PROP_URL))
        if (name, url) in seen:
            continue
        seen.add((name, url))
        audience = [
            a.strip()
            for seg in (props.get(PROP_AUDIENCE) or [])
            if isinstance(seg, list) and isinstance(seg[0], str)
            for a in seg[0].split(",")
            if a.strip()
        ]
        rows.append(
            {
                "name": name,
                "description": plain(props.get(PROP_DESCRIPTION)),
                "url": url,
                "author": plain(props.get(PROP_AUTHOR)),
                "audience": sorted(set(audience)),
                "categories": sorted(
                    {
                        folder_names[f]
                        for f in relation_ids(props.get(PROP_FOLDER))
                        if folder_names.get(f)
                    }
                ),
            }
        )

    if args.check_links:
        urls = sorted({r["url"] for r in rows if r["url"]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
            statuses = dict(zip(urls, ex.map(check_link, urls)))
        for r in rows:
            r["http_status"] = statuses.get(r["url"])

    Path(args.out).write_text(
        json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} rows to {args.out}")
    print(
        "top categories:",
        Counter(c for r in rows for c in r["categories"]).most_common(10),
    )


if __name__ == "__main__":
    main()
