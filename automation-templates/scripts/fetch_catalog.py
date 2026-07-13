#!/usr/bin/env python3
"""Fetch the '365+ Automation Templates' catalog from its public Notion site.

Source: https://ignacio-velasquez.notion.site/365-Automation-Templates-245087908e5447c2a1a2c66d8c90019c
(curated by Ignacio Velásquez, free/public list).

Pulls every row of the "Automation Ideas List" database through Notion's
public `queryCollection` API, resolves category folders, optionally checks
link liveness, and writes `catalog.json` next to this script's parent dir.

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
PAGE_ID = "24508790-8e54-47c2-a1a2-c66d8c90019c"
SPACE_ID = "60dcb895-9be7-418d-85ea-37835ad5cd95"
IDEAS_COLLECTION = "0d0da276-3456-4a23-8393-e40e9650c2e9"
IDEAS_VIEW = "f4b44d14-0920-45bd-abda-858af7759a93"
FOLDERS_COLLECTION = "9bc681d0-4d77-4fa4-9dec-ea19819b8048"
FOLDERS_VIEW = "633b55bb-6cbf-44dd-8c37-ec5363f6bbb8"

# Ideas-collection schema property keys (stable Notion internal ids)
PROP_DESCRIPTION = ":RNw"
PROP_FOLDER = "=?dV"
PROP_URL = "cypw"
PROP_TAG = "dr?V"

PLATFORM_BY_DOMAIN = {
    "bardeen.ai": "Bardeen",
    "make.com": "Make",
    "zapier.com": "Zapier",
    "ifttt.com": "IFTTT",
    "whalesync.com": "Whalesync",
    "pabbly.com": "Pabbly Connect",
    "integrately.com": "Integrately",
    "n8n.io": "n8n",
}


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


def query_collection(coll_id, view_id):
    return post(
        "queryCollection",
        {
            "source": {"type": "collection", "id": coll_id, "spaceId": SPACE_ID},
            "collectionView": {"id": view_id, "spaceId": SPACE_ID},
            "loader": {
                "type": "reducer",
                "reducers": {
                    "collection_group_results": {"type": "results", "limit": 2000}
                },
                "searchQuery": "",
                "userTimeZone": "UTC",
            },
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


def platform_of(url, name):
    if "|" in name:
        tail = name.rsplit("|", 1)[1].strip()
        if tail and len(tail) < 30:
            return tail
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, platform in PLATFORM_BY_DOMAIN.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return host or "?"


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

    ideas = query_collection(IDEAS_COLLECTION, IDEAS_VIEW)
    block_ids = ideas["result"]["reducerResults"]["collection_group_results"]["blockIds"]
    ideas_rm = ideas["recordMap"]["block"]

    rows = []
    for bid in block_ids:
        v = unwrap(ideas_rm.get(bid, {}))
        if not v:
            continue
        props = v.get("properties") or {}
        name = plain(props.get("title"))
        url = plain(props.get(PROP_URL))
        rows.append(
            {
                "name": name,
                "description": plain(props.get(PROP_DESCRIPTION)),
                "url": url,
                "tag": plain(props.get(PROP_TAG)),
                "categories": sorted(
                    {
                        folder_names[f]
                        for f in relation_ids(props.get(PROP_FOLDER))
                        if folder_names.get(f)
                    }
                ),
                "platform": platform_of(url, name),
            }
        )

    rows.sort(key=lambda r: (r["platform"].lower(), r["name"].lower()))

    if args.check_links:
        urls = sorted({r["url"] for r in rows if r["url"]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            statuses = dict(zip(urls, ex.map(check_link, urls)))
        for r in rows:
            r["http_status"] = statuses.get(r["url"])

    Path(args.out).write_text(
        json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} rows to {args.out}")
    print("by platform:", Counter(r["platform"] for r in rows).most_common())


if __name__ == "__main__":
    main()
