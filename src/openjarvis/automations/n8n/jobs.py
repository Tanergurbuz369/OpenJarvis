"""Scheduler job entry points for the n8n integration.

Registered in :data:`openjarvis.scheduler.jobs.BUILTIN_JOBS` as ``n8n_sync`` so
a scheduled task can keep the catalog fresh and auto-install newly added
workflows without any LLM involvement.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path("~/.openjarvis/n8n").expanduser()


def run_sync_job(metadata: Dict[str, Any]) -> str:
    """Sync the n8n catalog, optionally download, then auto-install new workflows.

    Recognized ``metadata`` keys (all optional):

    - ``root``: catalog/library root (default ``~/.openjarvis/n8n``)
    - ``max_pages``: limit pages fetched (default: all)
    - ``rows``: workflows per page (default 100)
    - ``download_limit``: also download the top-N catalog entries to the library
    - ``install``: run the auto-installer afterwards (default ``True``)
    - ``install_from_catalog``: install *every* catalogued workflow (metadata
      only) rather than just downloaded library files (default ``False``)
    - ``templates_dir``: where generated templates are written
    """
    from openjarvis.automations.n8n.installer import N8nAutoInstaller
    from openjarvis.automations.n8n.sync import N8nLibrarySync

    root = Path(metadata.get("root") or DEFAULT_ROOT).expanduser()
    max_pages: Optional[int] = metadata.get("max_pages")
    rows = int(metadata.get("rows") or 100)
    download_limit: Optional[int] = metadata.get("download_limit")
    do_install = metadata.get("install", True)
    install_from_catalog = metadata.get("install_from_catalog", False)
    templates_dir = metadata.get("templates_dir")

    parts = []
    catalog = None
    syncer = N8nLibrarySync(root)
    try:
        catalog = syncer.sync_catalog(rows=rows, max_pages=max_pages)
        parts.append(
            f"catalog: {len(catalog)} indexed / {catalog.total_available} upstream"
        )
        if download_limit:
            paths = syncer.download_all(limit=int(download_limit))
            parts.append(f"downloaded: {len(paths)}")
    finally:
        syncer.close()

    if do_install:
        installer = N8nAutoInstaller(
            root / "library",
            templates_dir=Path(templates_dir).expanduser() if templates_dir else None,
        )
        if install_from_catalog and catalog is not None:
            results = installer.install_from_catalog(catalog)
        else:
            results = installer.install_new()
        new = [r for r in results if r.status == "installed"]
        updated = [r for r in results if r.status == "updated"]
        parts.append(f"installed: {len(new)} new, {len(updated)} updated")

    summary = " | ".join(parts)
    logger.info("n8n_sync job: %s", summary)
    return summary


__all__ = ["run_sync_job"]
