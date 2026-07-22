"""Test the n8n_sync scheduler job end-to-end with a fake API client."""

from __future__ import annotations

from openjarvis.automations.n8n import jobs as n8n_jobs
from openjarvis.automations.n8n.sync import N8nLibrarySync


class FakeClient:
    def __init__(self, records):
        self._records = records

    def total_workflows(self):
        return len(self._records)

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
        pass


def test_run_sync_job_syncs_downloads_installs(tmp_path, monkeypatch):
    records = [
        {
            "id": 1,
            "name": "Job Alpha",
            "description": "a",
            "user": {"name": "X"},
            "nodes": [{"type": "n8n-nodes-base.set"}],
            "totalViews": 9,
        },
    ]

    # Force N8nLibrarySync to use the fake client regardless of constructor args.
    real_init = N8nLibrarySync.__init__

    def patched_init(self, root, *, client=None):
        real_init(self, root, client=FakeClient(records))

    monkeypatch.setattr(N8nLibrarySync, "__init__", patched_init)

    root = tmp_path / "n8n"
    templates = tmp_path / "templates"
    summary = n8n_jobs.run_sync_job(
        {
            "root": str(root),
            "download_limit": 1,
            "install": True,
            "templates_dir": str(templates),
        }
    )

    assert "catalog: 1 indexed" in summary
    assert "downloaded: 1" in summary
    assert "installed: 1 new" in summary

    # Catalog + library + generated template all exist on disk.
    assert (root / "catalog.json").exists()
    assert list((root / "library").glob("*.workflow.json"))
    assert list(templates.glob("n8n_*.toml"))
