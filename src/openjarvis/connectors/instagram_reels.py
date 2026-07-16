"""Instagram Reels connector — public reel metadata via Open Graph tags.

Fetches public Instagram Reels and normalizes them to ``Document`` objects.
No authentication is required for public reels: the connector reads the
Open Graph meta tags (``og:title``, ``og:description``, ``og:image``,
``og:video``) that Instagram serves in the reel page's HTML.

All network access lives in module-level functions so it can be mocked in
tests, matching the ``hackernews`` and ``news_rss`` connectors.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import httpx

from openjarvis.connectors._stubs import BaseConnector, Document, SyncStatus
from openjarvis.core.config import DEFAULT_CONFIG_DIR
from openjarvis.core.registry import ConnectorRegistry

_DEFAULT_CONFIG_PATH = str(DEFAULT_CONFIG_DIR / "connectors" / "instagram_reels.json")

# Seed reel to integrate out of the box.  Used when no config file exists and
# no explicit list of reels is supplied.
_SEED_REEL_URL = "https://www.instagram.com/reel/Dasea7gNCB2/"

# A browser-like User-Agent helps Instagram return the Open Graph tags.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# Matches the shortcode in /reel/<code>/, /reels/<code>/ or /p/<code>/ URLs.
_SHORTCODE_RE = re.compile(r"instagram\.com/(?:reels?|p)/([A-Za-z0-9_-]+)")


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

    return {
        "caption": caption,
        "author": author,
        "description": description,
        "thumbnail_url": _meta_content(page_html, "og:image"),
        "video_url": _meta_content(page_html, "og:video"),
        "likes": likes,
        "comments": comments,
    }


@ConnectorRegistry.register("instagram_reels")
class InstagramReelsConnector(BaseConnector):
    """Ingest public Instagram Reels as ``Document`` objects.

    Reels can be supplied three ways (highest precedence first):

    1. The ``reels`` constructor argument (list of URLs or shortcodes).
    2. A JSON config file at ``config_path`` with a ``{"reels": [...]}`` key.
    3. The built-in seed reel, so the connector works out of the box.
    """

    connector_id = "instagram_reels"
    display_name = "Instagram Reels"
    auth_type = "local"

    def __init__(
        self,
        *,
        reels: Optional[List[str]] = None,
        config_path: str = _DEFAULT_CONFIG_PATH,
    ) -> None:
        self._reels = reels
        self._config_path = Path(config_path)
        self._status = SyncStatus()

    def _resolve_reels(self) -> List[str]:
        """Return the list of reel URLs/shortcodes to sync."""
        if self._reels is not None:
            return self._reels
        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                configured = data.get("reels", [])
                if configured:
                    return configured
            except (json.JSONDecodeError, OSError):
                pass
        return [_SEED_REEL_URL]

    def is_connected(self) -> bool:
        # Local connector with no credentials; usable whenever reels resolve.
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
                page_html = _fetch_reel_html(shortcode)
            except httpx.HTTPError:
                continue

            meta = _parse_og_metadata(page_html)
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
                },
            )

        self._status.state = "idle"
        self._status.last_sync = datetime.now()

    def sync_status(self) -> SyncStatus:
        return self._status
