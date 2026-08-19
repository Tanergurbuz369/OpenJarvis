"""Tests for toast-1-backed research retrieval (MixedbreadSearch + sync).

Same approach as the MixedbreadMemory backend tests: the classes are
adapters over the ``mixedbread`` SDK, so a fake client exercises argument
mapping, local hydration, filter semantics, fallback behavior, and sync
idempotency offline. Skipped when the optional SDK is not installed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

pytest.importorskip("mixedbread")

from openjarvis.connectors.hybrid_search import HybridSearch, build_research_search
from openjarvis.connectors.mixedbread_search import (
    MixedbreadKnowledgeSync,
    MixedbreadSearch,
)
from openjarvis.connectors.store import KnowledgeStore
from openjarvis.core.config import JarvisConfig


def _chunk(
    *,
    external_id: Optional[str],
    text: str = "remote text",
    score: float = 0.9,
    file_id: str = "file_1",
    filename: str = "chunk.md",
    chunk_index: int = 0,
    metadata: Any = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        external_id=external_id,
        text=text,
        score=score,
        file_id=file_id,
        filename=filename,
        chunk_index=chunk_index,
        metadata=metadata,
    )


class FakeStores:
    def __init__(self) -> None:
        self.files = self
        self.search_results: List[SimpleNamespace] = []
        self.search_calls: List[Dict[str, Any]] = []
        self.upload_calls: List[Dict[str, Any]] = []
        self.search_error: Optional[Exception] = None

    def retrieve(self, store_identifier: str) -> SimpleNamespace:
        return SimpleNamespace(id="kstore_1")

    def search(self, **kwargs: Any) -> SimpleNamespace:
        self.search_calls.append(kwargs)
        if self.search_error is not None:
            raise self.search_error
        return SimpleNamespace(data=list(self.search_results))

    def upload(self, **kwargs: Any) -> SimpleNamespace:
        self.upload_calls.append(kwargs)
        return SimpleNamespace(id=f"file_{len(self.upload_calls)}")


class FakeClient:
    def __init__(self) -> None:
        self.stores = FakeStores()


def _seed(store: KnowledgeStore, content: str, *, source: str = "gmail", **kw) -> str:
    return store.store(
        content=content, source=source, doc_id=f"doc-{content[:8]}", **kw
    )


def test_search_hydrates_local_rows_in_remote_rank_order() -> None:
    store = KnowledgeStore(db_path=":memory:")
    id_a = _seed(store, "Quarterly revenue grew twelve percent.", title="Q3 report")
    id_b = _seed(store, "The offsite is in Lisbon this year.", title="Offsite plan")

    client = FakeClient()
    client.stores.search_results = [
        _chunk(external_id=id_b, score=0.95),
        _chunk(external_id=id_a, score=0.60),
    ]
    search = MixedbreadSearch(store, client=client)

    hits = search.search("where is the offsite?", limit=5)

    assert [h.chunk_id for h in hits] == [id_b, id_a]
    assert hits[0].title == "Offsite plan"
    assert "Lisbon" in hits[0].content_snippet
    assert hits[0].score == pytest.approx(0.95)
    assert hits[0].source == "gmail"

    (call,) = client.stores.search_calls
    assert call["store_identifiers"] == ["kstore_1"]
    assert call["top_k"] == 15  # limit * default overfetch of 3
    assert call["search_options"]["agentic"] is True


def test_search_applies_structured_filters_locally() -> None:
    store = KnowledgeStore(db_path=":memory:")
    id_mail = _seed(store, "Mail about the launch date.", source="gmail")
    id_slack = _seed(store, "Slack chatter about the launch.", source="slack")

    client = FakeClient()
    client.stores.search_results = [
        _chunk(external_id=id_slack, score=0.9),
        _chunk(external_id=id_mail, score=0.8),
    ]
    search = MixedbreadSearch(store, client=client)

    hits = search.search("launch date", sources=["gmail"], limit=5)

    assert [h.chunk_id for h in hits] == [id_mail]


def test_search_falls_back_to_hybrid_on_api_error() -> None:
    store = KnowledgeStore(db_path=":memory:")
    _seed(store, "The telemetry cluster SLA is now 99.95 percent.")

    client = FakeClient()
    client.stores.search_error = RuntimeError("api down")
    fallback = HybridSearch(store, None)
    search = MixedbreadSearch(store, client=client, fallback=fallback)

    hits = search.search("telemetry SLA", limit=5)

    assert hits, "fallback should serve results when the API fails"
    assert "99.95" in hits[0].content_snippet


def test_search_error_without_fallback_propagates() -> None:
    store = KnowledgeStore(db_path=":memory:")
    client = FakeClient()
    client.stores.search_error = RuntimeError("api down")
    search = MixedbreadSearch(store, client=client)

    with pytest.raises(RuntimeError, match="api down"):
        search.search("anything")


def test_empty_query_delegates_to_fallback_not_api() -> None:
    store = KnowledgeStore(db_path=":memory:")
    _seed(store, "Recent snapshot row.")

    client = FakeClient()
    search = MixedbreadSearch(store, client=client, fallback=HybridSearch(store, None))

    hits = search.search("   ", limit=5)

    assert hits, "metadata-only query should hit the local fallback"
    assert client.stores.search_calls == []


def test_unmatched_remote_file_synthesizes_hit_only_unfiltered() -> None:
    store = KnowledgeStore(db_path=":memory:")
    client = FakeClient()
    client.stores.search_results = [
        _chunk(
            external_id=None,
            text="Directly uploaded doc.",
            filename="direct.md",
            metadata={"source": "upload"},
        ),
    ]
    search = MixedbreadSearch(store, client=client)

    hits = search.search("direct", limit=5)
    assert len(hits) == 1
    assert hits[0].source == "upload"
    assert hits[0].title == "direct.md"

    # With structured filters we cannot verify the remote-only file, so
    # it must be suppressed rather than bypass the filter.
    assert search.search("direct", sources=["gmail"], limit=5) == []


def test_sync_uploads_live_chunks_idempotently() -> None:
    store = KnowledgeStore(db_path=":memory:")
    id_a = _seed(store, "Keep me.", title="A")
    id_b = _seed(store, "Keep me too.", title="B")
    id_gone = _seed(store, "Soft deleted.", title="C")
    store._conn.execute(
        "UPDATE knowledge_chunks SET deleted_at = 1.0 WHERE id = ?", (id_gone,)
    )

    client = FakeClient()
    sync = MixedbreadKnowledgeSync(store, client=client)

    dry = sync.sync(dry_run=True)
    assert (dry.total, dry.uploaded, dry.dry_run) == (2, 0, True)
    assert client.stores.upload_calls == []

    report = sync.sync()
    assert (report.total, report.uploaded, report.failed) == (2, 2, 0)
    by_ext = {c["external_id"]: c for c in client.stores.upload_calls}
    assert set(by_ext) == {id_a, id_b}
    call = by_ext[id_a]
    assert call["overwrite"] is True
    assert call["store_identifier"] == "kstore_1"
    filename, payload = call["file"]
    assert filename == f"{id_a}.md"
    body = payload.decode("utf-8")
    assert "# A" in body and "Keep me." in body
    assert call["metadata"]["source"] == "gmail"


def test_build_research_search_defaults_to_hybrid() -> None:
    store = KnowledgeStore(db_path=":memory:")
    search = build_research_search(store, None, JarvisConfig())
    assert isinstance(search, HybridSearch)


def test_build_research_search_without_key_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MXBAI_API_KEY", raising=False)
    store = KnowledgeStore(db_path=":memory:")
    config = JarvisConfig()
    config.deep_research.retrieval = "mixedbread"

    search = build_research_search(store, None, config)

    assert isinstance(search, HybridSearch)


def test_build_research_search_mixedbread_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MXBAI_API_KEY", "test-key")
    store = KnowledgeStore(db_path=":memory:")
    config = JarvisConfig()
    config.deep_research.retrieval = "mixedbread"
    config.deep_research.mixedbread_store = "custom-store"

    search = build_research_search(store, None, config)

    assert isinstance(search, MixedbreadSearch)
    assert search._store_name == "custom-store"
    assert search._store is store  # ResearchAgent reads ._store for sources
    assert isinstance(search._fallback, HybridSearch)
