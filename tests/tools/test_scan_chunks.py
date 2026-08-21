"""Tests for ScanChunksTool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openjarvis.connectors.store import KnowledgeStore
from openjarvis.core.registry import ToolRegistry


@pytest.fixture()
def store(tmp_path: Path) -> KnowledgeStore:
    ks = KnowledgeStore(str(tmp_path / "test.db"))
    ks.store("Met with Sequoia about Series A", source="granola", doc_type="document")
    ks.store("Fundraising discussion with a16z", source="granola", doc_type="document")
    ks.store("Weekly standup notes", source="granola", doc_type="document")
    ks.store("Trip to Spain with family", source="imessage", doc_type="message")
    return ks


def _fake_engine() -> MagicMock:
    engine = MagicMock()
    engine.generate.return_value = {
        "content": "Found: Sequoia Series A discussion, a16z fundraising",
        "usage": {},
    }
    return engine


def test_scan_finds_semantic_matches(store: KnowledgeStore) -> None:
    from openjarvis.tools.scan_chunks import ScanChunksTool

    engine = _fake_engine()
    tool = ScanChunksTool(store=store, engine=engine, model="test")
    result = tool.execute(question="Which VCs have I spoken with?")
    assert result.success
    assert "Sequoia" in result.content or "Found" in result.content
    assert engine.generate.called


def test_scan_respects_source_filter(store: KnowledgeStore) -> None:
    from openjarvis.tools.scan_chunks import ScanChunksTool

    engine = _fake_engine()
    tool = ScanChunksTool(store=store, engine=engine, model="test")
    result = tool.execute(question="What trips?", source="imessage")
    assert result.success
    call_args = engine.generate.call_args
    messages = call_args[0][0] if call_args[0] else call_args[1].get("messages", [])
    all_content = str(messages)
    assert "Spain" in all_content


def test_scan_enforces_google_account_scope_and_hides_deleted_rows(
    tmp_path: Path,
) -> None:
    from openjarvis.tools.scan_chunks import ScanChunksTool

    store = KnowledgeStore(str(tmp_path / "scoped.db"))
    store.store(
        "WORK_ALLOWED",
        source="gmail",
        source_id="work:message",
        metadata={"account": "work"},
    )
    store.store(
        "PERSONAL_SECRET",
        source="gdrive",
        source_id="personal:file",
        metadata={"account": "personal"},
    )
    deleted_id = store.store(
        "DELETED_SECRET",
        source="slack",
        source_id="deleted",
    )
    store._conn.execute(
        "UPDATE knowledge_chunks SET deleted_at = '2026-01-01' WHERE id = ?",
        (deleted_id,),
    )
    store._conn.commit()
    engine = _fake_engine()

    result = ScanChunksTool(
        store=store,
        engine=engine,
        model="test",
        accounts=["work"],
    ).execute(question="find the marker")

    assert result.success
    messages = str(engine.generate.call_args.args[0])
    assert "WORK_ALLOWED" in messages
    assert "PERSONAL_SECRET" not in messages
    assert "DELETED_SECRET" not in messages
    store.close()


def test_scan_empty_store(tmp_path: Path) -> None:
    from openjarvis.tools.scan_chunks import ScanChunksTool

    ks = KnowledgeStore(str(tmp_path / "empty.db"))
    engine = _fake_engine()
    tool = ScanChunksTool(store=ks, engine=engine, model="test")
    result = tool.execute(question="Anything?")
    assert result.success
    assert "no chunks" in result.content.lower() or result.content == ""


def test_registered() -> None:
    from openjarvis.tools.scan_chunks import ScanChunksTool

    ToolRegistry.register_value("scan_chunks", ScanChunksTool)
    assert ToolRegistry.contains("scan_chunks")
