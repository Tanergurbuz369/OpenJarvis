"""Tests for InstagramReelsConnector — public reel Open Graph parsing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from openjarvis.connectors._stubs import Document
from openjarvis.core.registry import ConnectorRegistry

# Sample HTML with the Open Graph tags Instagram serves for a public reel.
_OG_DESCRIPTION = (
    "12.3K likes, 456 comments - cooldev on July 1, 2024: "
    "&quot;Building a local AI agent in 60 seconds &#128293;&quot;"
)
_SAMPLE_HTML = f"""
<html><head>
<meta property="og:url" content="https://www.instagram.com/reel/Dasea7gNCB2/" />
<meta property="og:title"
      content="cooldev on Instagram: &quot;Building a local AI agent&quot;" />
<meta property="og:description" content="{_OG_DESCRIPTION}" />
<meta property="og:image" content="https://scontent.cdninstagram.com/thumb.jpg" />
<meta property="og:video" content="https://scontent.cdninstagram.com/reel.mp4" />
</head><body></body></html>
"""


def test_instagram_reels_registered():
    """InstagramReelsConnector is discoverable via ConnectorRegistry."""
    from openjarvis.connectors.instagram_reels import InstagramReelsConnector

    ConnectorRegistry.register_value("instagram_reels", InstagramReelsConnector)
    assert ConnectorRegistry.contains("instagram_reels")
    cls = ConnectorRegistry.get("instagram_reels")
    assert cls.connector_id == "instagram_reels"
    assert cls.auth_type == "local"


@pytest.fixture()
def connector():
    from openjarvis.connectors.instagram_reels import InstagramReelsConnector

    # Point config at a non-existent path so the seed reel is used by default.
    return InstagramReelsConnector(config_path="/nonexistent/instagram_reels.json")


def test_extract_shortcode_from_variants():
    from openjarvis.connectors.instagram_reels import _extract_shortcode

    assert (
        _extract_shortcode("https://www.instagram.com/reel/Dasea7gNCB2/")
        == "Dasea7gNCB2"
    )
    assert (
        _extract_shortcode("https://www.instagram.com/reel/Dasea7gNCB2/?igsh=abc")
        == "Dasea7gNCB2"
    )
    assert _extract_shortcode("https://www.instagram.com/p/ABC123/") == "ABC123"
    assert _extract_shortcode("Dasea7gNCB2") == "Dasea7gNCB2"


def test_parse_og_metadata():
    from openjarvis.connectors.instagram_reels import _parse_og_metadata

    meta = _parse_og_metadata(_SAMPLE_HTML)
    assert meta["author"] == "cooldev"
    assert "Building a local AI agent in 60 seconds" in meta["caption"]
    assert meta["thumbnail_url"] == "https://scontent.cdninstagram.com/thumb.jpg"
    assert meta["video_url"] == "https://scontent.cdninstagram.com/reel.mp4"
    assert meta["likes"] == 12_300
    assert meta["comments"] == 456


def test_is_connected_uses_seed_reel(connector):
    """With no config and no explicit reels, the seed reel makes it usable."""
    assert connector.is_connected() is True


def test_sync_yields_reel_document(connector):
    """Sync fetches and normalizes the seed reel into a Document."""
    with patch(
        "openjarvis.connectors.instagram_reels._fetch_reel_html",
        return_value=_SAMPLE_HTML,
    ):
        docs = list(connector.sync())

    assert len(docs) == 1
    doc = docs[0]
    assert isinstance(doc, Document)
    assert doc.source == "instagram_reels"
    assert doc.doc_type == "reel"
    assert doc.doc_id == "instagram-reel-Dasea7gNCB2"
    assert doc.author == "cooldev"
    assert doc.title == "Reel by @cooldev"
    assert "Building a local AI agent" in doc.content
    assert doc.url == "https://www.instagram.com/reel/Dasea7gNCB2/"
    assert doc.metadata["shortcode"] == "Dasea7gNCB2"
    assert doc.metadata["video_url"].endswith("reel.mp4")
    assert doc.metadata["likes"] == 12_300


def test_sync_with_explicit_reels():
    """An explicit reels list overrides config and seed."""
    from openjarvis.connectors.instagram_reels import InstagramReelsConnector

    conn = InstagramReelsConnector(reels=["https://www.instagram.com/reel/XYZ999/"])
    with patch(
        "openjarvis.connectors.instagram_reels._fetch_reel_html",
        return_value=_SAMPLE_HTML,
    ) as mock_fetch:
        docs = list(conn.sync())

    mock_fetch.assert_called_once_with("XYZ999")
    assert len(docs) == 1
    assert docs[0].metadata["shortcode"] == "XYZ999"


def test_sync_skips_http_errors(connector):
    """A reel that fails to fetch is skipped, not fatal."""
    import httpx

    with patch(
        "openjarvis.connectors.instagram_reels._fetch_reel_html",
        side_effect=httpx.HTTPError("boom"),
    ):
        docs = list(connector.sync())

    assert docs == []
