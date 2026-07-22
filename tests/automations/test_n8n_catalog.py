"""Tests for the n8n catalog model."""

from __future__ import annotations

from openjarvis.automations.n8n.catalog import (
    Catalog,
    CatalogEntry,
    _slugify,
    _truncate,
)


def _api_record(**over):
    base = {
        "id": 42,
        "name": "Build Your First AI Agent",
        "description": "A long " + "x" * 400 + " description",
        "user": {"name": "Jane Doe"},
        "categories": [{"name": "AI"}, {"name": "Sales"}],
        "nodes": [{"type": "n8n-nodes-base.set"}, {"type": "n8n-nodes-base.if"}],
        "totalViews": 1234,
        "createdAt": "2024-01-01T00:00:00Z",
    }
    base.update(over)
    return base


def test_slugify_basic():
    assert _slugify("Build Your First AI Agent!") == "build-your-first-ai-agent"
    assert _slugify("") == "workflow"


def test_truncate_word_boundary():
    assert _truncate("short text") == "short text"
    long = "word " * 100
    out = _truncate(long, 50)
    assert len(out) <= 51 and out.endswith("…")


def test_entry_from_api_populates_and_truncates():
    e = CatalogEntry.from_api(_api_record())
    assert e.id == 42
    assert e.author == "Jane Doe"
    assert e.categories == ["AI", "Sales"]
    assert e.nodes == 2
    assert e.total_views == 1234
    assert e.slug == "build-your-first-ai-agent"
    assert e.url == "https://n8n.io/workflows/42/"
    assert len(e.description) <= 201  # truncated


def test_entry_nodes_as_int():
    e = CatalogEntry.from_api(_api_record(nodes=7))
    assert e.nodes == 7


def test_entry_dict_roundtrip():
    e = CatalogEntry.from_api(_api_record())
    e2 = CatalogEntry.from_dict(e.to_dict())
    assert e2 == e


def test_library_filename():
    e = CatalogEntry.from_api(_api_record())
    assert e.library_filename() == "42-build-your-first-ai-agent.workflow.json"


def test_catalog_upsert_and_sort(tmp_path):
    cat = Catalog(total_available=100)
    cat.upsert(CatalogEntry.from_api(_api_record(id=1, totalViews=10)))
    cat.upsert(CatalogEntry.from_api(_api_record(id=2, totalViews=99)))
    cat.upsert(CatalogEntry.from_api(_api_record(id=1, totalViews=50)))  # update
    assert len(cat) == 2
    assert 1 in cat and 2 in cat
    ordered = cat.sorted_entries()
    assert ordered[0].id == 2  # most viewed first

    path = tmp_path / "catalog.json"
    cat.save(path)
    loaded = Catalog.load(path)
    assert len(loaded) == 2
    assert loaded.total_available == 100
    assert loaded.entries[1].total_views == 50


def test_load_missing_catalog_returns_empty(tmp_path):
    cat = Catalog.load(tmp_path / "nope.json")
    assert len(cat) == 0
    assert cat.total_available == 0
