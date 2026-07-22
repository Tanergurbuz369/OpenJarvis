"""Sync the n8n template catalog and download full workflows on demand."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from openjarvis.automations.n8n.catalog import Catalog, CatalogEntry
from openjarvis.automations.n8n.client import N8nTemplateClient

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class N8nLibrarySync:
    """Mirror the n8n template library into a local catalog + workflow files.

    Layout under *root*::

        root/
          catalog.json          # lightweight index of every known workflow
          library/              # full importable workflow JSON, downloaded
            <id>-<slug>.workflow.json
    """

    def __init__(
        self,
        root: str | Path,
        *,
        client: Optional[N8nTemplateClient] = None,
    ) -> None:
        self.root = Path(root)
        self.catalog_path = self.root / "catalog.json"
        self.library_dir = self.root / "library"
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> N8nTemplateClient:
        if self._client is None:
            self._client = N8nTemplateClient()
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    # -- catalog -------------------------------------------------------
    def load_catalog(self) -> Catalog:
        return Catalog.load(self.catalog_path)

    def sync_catalog(
        self,
        *,
        rows: int = 100,
        max_pages: Optional[int] = None,
        search: Optional[str] = None,
        category: Optional[int] = None,
        progress: Optional[ProgressFn] = None,
        merge: bool = True,
    ) -> Catalog:
        """Fetch workflow metadata across pages and persist the catalog.

        Set ``max_pages=None`` for a full mirror of all ~10k+ workflows, or a
        small number for a bounded sync. When *merge* is true, existing catalog
        entries are preserved and updated in place.
        """
        client = self._get_client()
        catalog = self.load_catalog() if merge else Catalog()
        total = client.total_workflows()
        catalog.total_available = total
        added = 0
        for wf in client.iter_workflows(
            rows=rows, search=search, category=category, max_pages=max_pages
        ):
            try:
                entry = CatalogEntry.from_api(wf)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("skipping malformed workflow entry: %s", exc)
                continue
            catalog.upsert(entry)
            added += 1
            if progress is not None:
                progress(added, total)
        catalog.synced_at = _utcnow_iso()
        catalog.save(self.catalog_path)
        logger.info(
            "catalog synced: %d entries indexed (%d available upstream)",
            len(catalog),
            total,
        )
        return catalog

    # -- library -------------------------------------------------------
    @staticmethod
    def _to_importable(detail: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an API detail object into an importable n8n workflow."""
        graph = detail.get("workflow")
        if not isinstance(graph, dict) or "nodes" not in graph:
            # Some responses already are the graph.
            graph = detail if "nodes" in detail else {"nodes": [], "connections": {}}
        graph = dict(graph)
        graph.setdefault("name", detail.get("name") or "Imported workflow")
        graph.setdefault("connections", {})
        graph.setdefault("settings", {"executionOrder": "v1"})
        graph.setdefault("active", False)
        user = detail.get("user") or {}
        meta = dict(graph.get("meta") or {})
        meta.setdefault("owner", user.get("name") or user.get("username") or "n8n.io")
        meta.setdefault("source", "n8n.io template library")
        meta.setdefault("templateId", detail.get("id"))
        graph["meta"] = meta
        return graph

    def download_workflow(self, entry_or_id: CatalogEntry | int) -> Path:
        """Download one workflow's full JSON into the library. Returns its path."""
        client = self._get_client()
        if isinstance(entry_or_id, CatalogEntry):
            entry = entry_or_id
        else:
            detail = client.get_workflow(int(entry_or_id))
            entry = CatalogEntry.from_api(detail)
        detail = client.get_workflow(entry.id)
        graph = self._to_importable(detail)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        path = self.library_dir / entry.library_filename()
        path.write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def download_all(
        self,
        entries: Optional[Iterable[CatalogEntry]] = None,
        *,
        limit: Optional[int] = None,
        skip_existing: bool = True,
        progress: Optional[ProgressFn] = None,
    ) -> List[Path]:
        """Download full JSON for many catalog entries into the library."""
        catalog = self.load_catalog()
        items = list(entries) if entries is not None else catalog.sorted_entries()
        if limit is not None:
            items = items[:limit]
        paths: List[Path] = []
        total = len(items)
        for i, entry in enumerate(items, start=1):
            target = self.library_dir / entry.library_filename()
            if skip_existing and target.exists():
                paths.append(target)
            else:
                try:
                    paths.append(self.download_workflow(entry))
                except Exception as exc:  # keep going on individual failures
                    logger.warning("failed to download workflow %s: %s", entry.id, exc)
            if progress is not None:
                progress(i, total)
        return paths
