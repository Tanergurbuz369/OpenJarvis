"""Instagram Reels connector — public reel metadata for Deep Research.

Fetches Instagram Reels and normalizes them to ``Document`` objects using a
fallback chain of strategies, richest first:

1. **Apify** — runs an Instagram scraper actor (needs an Apify API token).
   Returns full metadata: caption, author, video URL, likes, comments.
2. **oEmbed** — Instagram's official oEmbed endpoint (needs a Facebook app
   access token). Returns author and thumbnail; no video URL or counts.
3. **Open Graph** — scrapes the public reel page's ``og:*`` meta tags. No
   authentication required, but Instagram may gate pages behind a login wall.

Tokens are optional: with none configured the connector falls back to the
Open Graph path and still works for public reels. All network access lives
in module-level functions so it can be mocked in tests, matching the
``hackernews`` and ``weather`` connectors.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

from openjarvis.connectors._stubs import BaseConnector, Document, SyncStatus
from openjarvis.core.config import DEFAULT_CONFIG_DIR
from openjarvis.core.registry import ConnectorRegistry

_DEFAULT_CONFIG_PATH = str(DEFAULT_CONFIG_DIR / "connectors" / "instagram_reels.json")

# Seed reel to integrate out of the box.  Used when no config file exists and
# no explicit list of reels is supplied.
_SEED_REEL_URL = "https://www.instagram.com/reel/Dasea7gNCB2/"

# Default Apify actor for Instagram scraping (slug uses '/', converted to '~'
# for the API path at call time).
_DEFAULT_APIFY_ACTOR = "apify/instagram-scraper"

# Environment variables used as a last-resort source for tokens.
_ENV_APIFY_TOKEN = "OPENJARVIS_INSTAGRAM_APIFY_TOKEN"
_ENV_OEMBED_TOKEN = "OPENJARVIS_INSTAGRAM_OEMBED_TOKEN"

# A browser-like User-Agent helps Instagram return the Open Graph tags.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# Matches the shortcode in /reel/<code>/, /reels/<code>/ or /p/<code>/ URLs.
_SHORTCODE_RE = re.compile(r"instagram\.com/(?:reels?|p)/([A-Za-z0-9_-]+)")

# Normalized metadata schema shared by every fetch strategy.
_EMPTY_META: Dict[str, Any] = {
    "caption": "",
    "author": "",
    "description": "",
    "thumbnail_url": "",
    "video_url": "",
    "likes": None,
    "comments": None,
}


def _extract_shortcode(url_or_code: str) -> str:
    """Return the Instagram shortcode for a reel URL or bare shortcode."""
    match = _SHORTCODE_RE.search(url_or_code)
    if match:
        return match.group(1)
    # Assume the caller passed a bare shortcode.
    return url_or_code.strip().strip("/")


def _canonical_reel_url(shortcode: str) -> str:
    """Return the canonical public URL for a reel shortcode."""
    return f"https://www.instagram.com/reel/{shortcode}/"


# --------------------------------------------------------------------------- #
# Strategy 1: Apify Instagram scraper actor
# --------------------------------------------------------------------------- #


def _normalize_apify_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map an Apify Instagram scraper item to the normalized meta schema."""
    caption = item.get("caption", "") or ""
    meta = dict(_EMPTY_META)
    meta.update(
        caption=caption,
        author=item.get("ownerUsername", "") or item.get("ownerFullName", ""),
        description=caption,
        thumbnail_url=item.get("displayUrl", "") or "",
        video_url=item.get("videoUrl", "") or "",
        likes=item.get("likesCount"),
        comments=item.get("commentsCount"),
    )
    return meta


def _fetch_via_apify(reel_url: str, token: str, actor: str) -> Optional[Dict[str, Any]]:
    """Fetch reel metadata by running an Apify actor synchronously.

    Returns the normalized meta dict, or ``None`` if the actor yields no items.
    """
    actor_path = actor.replace("/", "~")
    endpoint = f"https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items"
    resp = httpx.post(
        endpoint,
        params={"token": token},
        json={"directUrls": [reel_url], "resultsLimit": 1},
        timeout=120.0,
    )
    resp.raise_for_status()
    items = resp.json()
    if not items:
        return None
    return _normalize_apify_item(items[0])


# --------------------------------------------------------------------------- #
# Strategy 2: Instagram oEmbed (Facebook Graph API)
# --------------------------------------------------------------------------- #


def _normalize_oembed(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map an Instagram oEmbed response to the normalized meta schema."""
    title = data.get("title", "") or ""
    meta = dict(_EMPTY_META)
    meta.update(
        caption=title,
        author=data.get("author_name", "") or "",
        description=title,
        thumbnail_url=data.get("thumbnail_url", "") or "",
    )
    return meta


def _fetch_via_oembed(reel_url: str, token: str) -> Optional[Dict[str, Any]]:
    """Fetch reel metadata from Instagram's official oEmbed endpoint."""
    resp = httpx.get(
        "https://graph.facebook.com/v20.0/instagram_oembed",
        params={"url": reel_url, "access_token": token, "omitscript": "true"},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    return _normalize_oembed(data)


# --------------------------------------------------------------------------- #
# Strategy 3: Open Graph page scraping (no auth)
# --------------------------------------------------------------------------- #


def _fetch_reel_html(shortcode: str) -> str:
    """Download the public HTML for a reel by shortcode."""
    resp = httpx.get(
        _canonical_reel_url(shortcode),
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()
    return resp.text


def _meta_content(page_html: str, prop: str) -> str:
    """Extract the ``content`` of an Open Graph ``<meta>`` tag.

    Handles both attribute orders (``property`` before or after ``content``).
    """
    escaped = re.escape(prop)
    patterns = (
        rf'<meta[^>]+property=["\']{escaped}["\'][^>]+content=["\'](.*?)["\']',
        rf'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']{escaped}["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, page_html, re.IGNORECASE | re.DOTALL)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _parse_count(text: str) -> Optional[int]:
    """Parse a human-formatted count like ``12.3K`` or ``1,234`` into an int."""
    text = text.strip().replace(",", "")
    match = re.fullmatch(r"([\d.]+)\s*([KMB]?)", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[
        match.group(2).lower()
    ]
    return int(value * multiplier)


def _parse_og_metadata(page_html: str) -> Dict[str, Any]:
    """Extract reel fields from a page's Open Graph tags.

    Instagram's ``og:description`` typically looks like::

        1,234 likes, 56 comments - username on July 1, 2024: "caption text"
    """
    title = _meta_content(page_html, "og:title")
    description = _meta_content(page_html, "og:description")

    likes = comments = None
    like_match = re.search(r"([\d.,]+[KMB]?)\s+likes?", description, re.IGNORECASE)
    if like_match:
        likes = _parse_count(like_match.group(1))
    comment_match = re.search(
        r"([\d.,]+[KMB]?)\s+comments?", description, re.IGNORECASE
    )
    if comment_match:
        comments = _parse_count(comment_match.group(1))

    # Author: text between "- " and " on ..." in the description, else the
    # "<username> on Instagram" prefix of the title.
    author = ""
    author_match = re.search(r"-\s*(.+?)\s+on\b", description)
    if author_match:
        author = author_match.group(1).strip()
    if not author:
        title_match = re.search(r"^(.+?)\s+on\s+Instagram", title)
        if title_match:
            author = title_match.group(1).strip()

    # Caption: the quoted segment of the description, else the title.
    caption = ""
    caption_match = re.search(r':\s*"(.*)"\s*$', description, re.DOTALL)
    if caption_match:
        caption = caption_match.group(1).strip()
    if not caption:
        caption = title

    meta = dict(_EMPTY_META)
    meta.update(
        caption=caption,
        author=author,
        description=description,
        thumbnail_url=_meta_content(page_html, "og:image"),
        video_url=_meta_content(page_html, "og:video"),
        likes=likes,
        comments=comments,
    )
    return meta


@ConnectorRegistry.register("instagram_reels")
class InstagramReelsConnector(BaseConnector):
    """Ingest Instagram Reels as ``Document`` objects.

    Reels can be supplied three ways (highest precedence first):

    1. The ``reels`` constructor argument (list of URLs or shortcodes).
    2. A JSON config file at ``config_path`` with a ``{"reels": [...]}`` key.
    3. The built-in seed reel, so the connector works out of the box.

    Fetch strategy tokens (``apify_token``, ``oembed_token``, ``apify_actor``)
    likewise resolve from the constructor arg, then the config file, then the
    ``OPENJARVIS_INSTAGRAM_*`` environment variables.
    """

    connector_id = "instagram_reels"
    display_name = "Instagram Reels"
    auth_type = "local"

    def __init__(
        self,
        *,
        reels: Optional[List[str]] = None,
        config_path: str = _DEFAULT_CONFIG_PATH,
        apify_token: Optional[str] = None,
        oembed_token: Optional[str] = None,
        apify_actor: Optional[str] = None,
    ) -> None:
        self._reels = reels
        self._config_path = Path(config_path)
        self._apify_token_arg = apify_token
        self._oembed_token_arg = oembed_token
        self._apify_actor_arg = apify_actor
        self._status = SyncStatus()

    def _load_config(self) -> Dict[str, Any]:
        """Read the JSON config file, returning ``{}`` if absent/invalid."""
        if not self._config_path.exists():
            return {}
        try:
            return json.loads(self._config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _resolve_reels(self) -> List[str]:
        """Return the list of reel URLs/shortcodes to sync."""
        if self._reels is not None:
            return self._reels
        configured = self._load_config().get("reels", [])
        if configured:
            return configured
        return [_SEED_REEL_URL]

    def _apify_token(self) -> Optional[str]:
        return (
            self._apify_token_arg
            or self._load_config().get("apify_token")
            or os.getenv(_ENV_APIFY_TOKEN)
        )

    def _oembed_token(self) -> Optional[str]:
        return (
            self._oembed_token_arg
            or self._load_config().get("oembed_token")
            or os.getenv(_ENV_OEMBED_TOKEN)
        )

    def _apify_actor(self) -> str:
        return (
            self._apify_actor_arg
            or self._load_config().get("apify_actor")
            or _DEFAULT_APIFY_ACTOR
        )

    def _fetch_meta(self, shortcode: str) -> Tuple[Dict[str, Any], str]:
        """Resolve reel metadata via the strategy chain.

        Returns ``(meta, method)`` where *method* names the strategy that
        succeeded. Configured strategies fall through to the next on HTTP
        errors; the Open Graph fallback may raise ``httpx.HTTPError``.
        """
        reel_url = _canonical_reel_url(shortcode)

        apify_token = self._apify_token()
        if apify_token:
            try:
                meta = _fetch_via_apify(reel_url, apify_token, self._apify_actor())
                if meta:
                    return meta, "apify"
            except httpx.HTTPError:
                pass

        oembed_token = self._oembed_token()
        if oembed_token:
            try:
                meta = _fetch_via_oembed(reel_url, oembed_token)
                if meta:
                    return meta, "oembed"
            except httpx.HTTPError:
                pass

        page_html = _fetch_reel_html(shortcode)
        return _parse_og_metadata(page_html), "opengraph"

    def is_connected(self) -> bool:
        # Local connector with no required credentials; usable whenever reels
        # resolve.  Tokens only upgrade the fetch strategy.
        return len(self._resolve_reels()) > 0

    def disconnect(self) -> None:
        self._reels = None
        if self._config_path.exists():
            self._config_path.unlink()

    def sync(
        self, *, since: Optional[datetime] = None, cursor: Optional[str] = None
    ) -> Iterator[Document]:
        """Yield a Document for each configured reel."""
        for entry in self._resolve_reels():
            shortcode = _extract_shortcode(entry)
            if not shortcode:
                continue

            try:
                meta, method = self._fetch_meta(shortcode)
            except httpx.HTTPError:
                continue

            author = meta["author"]
            caption = meta["caption"]
            title = f"Reel by @{author}" if author else "Instagram Reel"

            yield Document(
                doc_id=f"instagram-reel-{shortcode}",
                source="instagram_reels",
                doc_type="reel",
                content=caption or meta["description"],
                title=title,
                author=author,
                timestamp=datetime.now(),
                url=_canonical_reel_url(shortcode),
                metadata={
                    "shortcode": shortcode,
                    "thumbnail_url": meta["thumbnail_url"],
                    "video_url": meta["video_url"],
                    "likes": meta["likes"],
                    "comments": meta["comments"],
                    "source_method": method,
                },
            )

        self._status.state = "idle"
        self._status.last_sync = datetime.now()

    def sync_status(self) -> SyncStatus:
        return self._status
