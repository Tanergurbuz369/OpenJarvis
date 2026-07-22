"""Tests for the n8n library sync using an injected fake client (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from openjarvis.automations.n8n.sync import N8nLibrarySync

N8N_DIR = Path(__file__).resolve().parents[2] / "automations" / "n8n"


class FakeClient:
    """In-memory stand-in for N8nTemplateClient."""

    def __init__(self, records, total=None):
        self._records = records
        self._total = total if total is not None else len(records)
        self.closed = False

    def total_workflows(self):
        return self._total

    def iter_workflows(self, *, rows=100, search=None, category=None, max_pages=None):
        yield from self._records

    def get_workflow(self, workflow_id):
        rec = next(r for r in self._records if r["id"] == int(workflow_id))
        return {
            "id": rec["id"],
            "name": rec["name"],
            "user": rec.get("user", {}),
            "workflow": {
                "nodes": [
                    {
                        "name": "Trigger",
                        "type": "n8n-nodes-base.scheduleTrigger",
                        "typeVersion": 1,
                        "position": [0, 0],
                    }
                ],
                "connections": {},
            },
        }

    def close(self):
        self.closed = True


def _records():
    return [
        {
            "id": 10,
            "name": "Alpha Flow",
            "description": "does alpha",
            "user": {"name": "A"},
            "nodes": [{"type": "n8n-nodes-base.set"}],
            "totalViews": 5,
        },
        {
            "id": 20,
            "name": "Beta Flow",
            "description": "does beta",
            "user": {"name": "B"},
            "nodes": [{"type": "n8n-nodes-base.if"}, {"type": "n8n-nodes-base.set"}],
            "totalViews": 50,
        },
    ]


def test_sync_catalog_writes_index(tmp_path):
    syncer = N8nLibrarySync(tmp_path, client=FakeClient(_records(), total=10760))
    cat = syncer.sync_catalog(merge=False)
    assert len(cat) == 2
    assert cat.total_available == 10760
    assert cat.synced_at is not None
    assert (tmp_path / "catalog.json").exists()

    reloaded = syncer.load_catalog()
    assert reloaded.sorted_entries()[0].id == 20  # most viewed first


def test_download_workflow_normalizes(tmp_path):
    syncer = N8nLibrarySync(tmp_path, client=FakeClient(_records()))
    syncer.sync_catalog(merge=False)
    path = syncer.download_workflow(20)
    assert path.name == "20-beta-flow.workflow.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    assert graph["name"] == "Beta Flow"
    assert "connections" in graph and "settings" in graph
    assert graph["meta"]["owner"] == "B"
    assert graph["meta"]["templateId"] == 20


def test_download_all_skips_existing(tmp_path):
    syncer = N8nLibrarySync(tmp_path, client=FakeClient(_records()))
    syncer.sync_catalog(merge=False)
    first = syncer.download_all(limit=2)
    assert len(first) == 2
    # Second run should skip existing files (no exception, same paths).
    again = syncer.download_all(limit=2, skip_existing=True)
    assert len(again) == 2


def test_committed_library_files_are_importable():
    """Every downloaded workflow in the repo library is import-shaped."""
    library = N8N_DIR / "library"
    files = sorted(library.glob("*.workflow.json"))
    assert files, "expected sample workflows committed under automations/n8n/library"
    for path in files:
        wf = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(wf.get("nodes"), list) and wf["nodes"], path.name
        assert isinstance(wf.get("connections"), dict), path.name
        # attribution is preserved from the upstream template
        assert wf.get("meta", {}).get("owner"), path.name
