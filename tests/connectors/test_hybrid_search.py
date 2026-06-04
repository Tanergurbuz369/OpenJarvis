"""Tests for source-aware HybridSearch behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from openjarvis.connectors.hybrid_search import HybridSearch
from openjarvis.connectors.store import KnowledgeStore


def _store_doc(
    store: KnowledgeStore,
    *,
    title: str,
    source: str,
    timestamp: datetime | str,
) -> None:
    timestamp_text = (
        timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    )
    store.store(
        content=f"Title: {title}\nWhen: {timestamp_text}",
        source=source,
        doc_type="event" if source == "gcalendar" else "email",
        doc_id=f"{source}:{title.lower().replace(' ', '-')}",
        title=title,
        timestamp=timestamp,
    )


def test_next_calendar_events_returns_nearest_gcalendar_rows() -> None:
    """Generic upcoming-calendar queries should be chronological timelines."""
    store = KnowledgeStore(db_path=":memory:")
    _store_doc(
        store,
        title="Calendar Digest Email",
        source="gmail",
        timestamp=datetime(2999, 1, 1, 9, tzinfo=timezone.utc),
    )
    _store_doc(
        store,
        title="Birthday Reminder",
        source="gcalendar",
        timestamp=datetime(2999, 12, 1, 9, tzinfo=timezone.utc),
    )
    _store_doc(
        store,
        title="Music Lesson",
        source="gcalendar",
        timestamp=datetime(2999, 5, 26, 18, tzinfo=timezone.utc),
    )
    _store_doc(
        store,
        title="Team Sync",
        source="gcalendar",
        timestamp=datetime(2999, 5, 27, 10, tzinfo=timezone.utc),
    )

    search = HybridSearch(store)
    hits = search.search("what are my next calendar events?", limit=2)
    contraction_hits = search.search("what's next on my calendar?", limit=2)
    meetings_hits = search.search("what are my next meetings?", limit=2)
    mixed_source_hits = search.search(
        "what are my next calendar events?",
        sources=["gmail", "gcalendar"],
        limit=2,
    )

    assert [hit.title for hit in hits] == ["Music Lesson", "Team Sync"]
    assert all(hit.source == "gcalendar" for hit in hits)
    assert [hit.title for hit in contraction_hits] == ["Music Lesson", "Team Sync"]
    assert all(hit.source == "gcalendar" for hit in contraction_hits)
    assert [hit.title for hit in meetings_hits] == ["Music Lesson", "Team Sync"]
    assert all(hit.source == "gcalendar" for hit in meetings_hits)
    assert [hit.title for hit in mixed_source_hits] == ["Music Lesson", "Team Sync"]
    assert all(hit.source == "gcalendar" for hit in mixed_source_hits)


def test_empty_upcoming_calendar_filter_uses_ascending_start_time() -> None:
    """Planner-emitted structured calendar searches return nearest first."""
    store = KnowledgeStore(db_path=":memory:")
    _store_doc(
        store,
        title="Later Event",
        source="gcalendar",
        timestamp=datetime(2999, 8, 1, 9, tzinfo=timezone.utc),
    )
    _store_doc(
        store,
        title="Sooner Event",
        source="gcalendar",
        timestamp=datetime(2999, 7, 1, 9, tzinfo=timezone.utc),
    )

    hits = HybridSearch(store).search(
        "",
        sources=["gcalendar"],
        time_range=(datetime(2999, 1, 1, tzinfo=timezone.utc), None),
        limit=2,
    )

    assert [hit.title for hit in hits] == ["Sooner Event", "Later Event"]


def test_upcoming_calendar_timeline_normalizes_timestamp_offsets() -> None:
    """Timeline filtering and ordering should compare instants, not ISO text."""
    store = KnowledgeStore(db_path=":memory:")
    _store_doc(
        store,
        title="Offset Earlier",
        source="gcalendar",
        timestamp="2999-07-01T00:30:00+02:00",
    )
    _store_doc(
        store,
        title="UTC Later",
        source="gcalendar",
        timestamp="2999-06-30T23:15:00+00:00",
    )

    search = HybridSearch(store)
    hits = search.search(
        "",
        sources=["gcalendar"],
        time_range=(datetime(2999, 6, 30, 22, tzinfo=timezone.utc), None),
        limit=2,
    )
    later_hits = search.search(
        "",
        sources=["gcalendar"],
        time_range=(datetime(2999, 6, 30, 23, tzinfo=timezone.utc), None),
        limit=2,
    )

    assert [hit.title for hit in hits] == ["Offset Earlier", "UTC Later"]
    assert [hit.title for hit in later_hits] == ["UTC Later"]


def test_upcoming_calendar_includes_today_all_day_events() -> None:
    """Upcoming calendar intent starts at the day boundary for all-day events."""
    store = KnowledgeStore(db_path=":memory:")
    _store_doc(
        store,
        title="All Day Today",
        source="gcalendar",
        timestamp="2999-07-01T00:00:00",
    )
    _store_doc(
        store,
        title="Morning Tomorrow",
        source="gcalendar",
        timestamp="2999-07-02T09:00:00+00:00",
    )

    hits = HybridSearch(store).search(
        "next calendar events",
        sources=["gcalendar"],
        time_range=(datetime(2999, 7, 1, 12, tzinfo=timezone.utc), None),
        limit=2,
    )
    local_tz_hits = HybridSearch(store).search(
        "",
        sources=["gcalendar"],
        time_range=(
            datetime(
                2999,
                7,
                1,
                12,
                tzinfo=timezone(timedelta(hours=-7)),
            ),
            None,
        ),
        limit=2,
    )

    assert [hit.title for hit in hits] == ["All Day Today", "Morning Tomorrow"]
    assert [hit.title for hit in local_tz_hits] == [
        "All Day Today",
        "Morning Tomorrow",
    ]


def _store(ks: KnowledgeStore, **kwargs) -> str:  # type: ignore[type-arg]
    defaults = {
        "content": "project alpha update",
        "source": "gmail",
        "doc_type": "email",
        "doc_id": None,
        "title": "",
        "author": "",
        "participants": None,
        "timestamp": "2026-01-01T00:00:00",
        "thread_id": None,
        "url": None,
        "metadata": None,
        "chunk_index": 0,
    }
    defaults.update(kwargs)
    return ks.store(**defaults)  # type: ignore[call-arg]


def test_hybrid_search_filters_by_account_alias(tmp_path: Path) -> None:
    """accounts=['work'] narrows all matching connectors to that profile."""
    ks = KnowledgeStore(db_path=tmp_path / "knowledge.db")
    _store(
        ks,
        content="project alpha renewal from work inbox",
        title="Work renewal",
        doc_id="gmail:work:1",
        metadata={"account": "work", "source_profile": "work"},
    )
    _store(
        ks,
        content="project alpha renewal from personal inbox",
        title="Personal renewal",
        doc_id="gmail:personal:1",
        metadata={"account": "personal", "source_profile": "personal"},
        chunk_index=1,
    )

    hits = HybridSearch(ks).search("project alpha renewal", accounts=["work"])

    assert hits
    assert {h.title for h in hits} == {"Work renewal"}
    assert all(h.account == "work" for h in hits)
    assert all(h.source_profile == "work" for h in hits)


def test_hybrid_search_intersects_sources_and_accounts(tmp_path: Path) -> None:
    """Connector and account filters combine for precise persona-scoped queries."""
    ks = KnowledgeStore(db_path=tmp_path / "knowledge.db")
    _store(
        ks,
        content="project alpha roadmap in work Gmail",
        source="gmail",
        title="Work Gmail roadmap",
        doc_id="gmail:work:1",
        metadata={"account": "work", "source_profile": "work"},
    )
    _store(
        ks,
        content="project alpha roadmap in work Drive",
        source="gdrive",
        doc_type="file",
        title="Work Drive roadmap",
        doc_id="gdrive:work:1",
        metadata={"account": "work", "source_profile": "work"},
        chunk_index=1,
    )
    _store(
        ks,
        content="project alpha roadmap in personal Drive",
        source="gdrive",
        doc_type="file",
        title="Personal Drive roadmap",
        doc_id="gdrive:personal:1",
        metadata={"account": "personal", "source_profile": "personal"},
        chunk_index=2,
    )

    hits = HybridSearch(ks).search(
        "project alpha roadmap",
        sources=["gdrive"],
        accounts=["work"],
    )

    assert hits
    assert {h.title for h in hits} == {"Work Drive roadmap"}
    assert all(h.source == "gdrive" for h in hits)
    assert all(h.account == "work" for h in hits)
