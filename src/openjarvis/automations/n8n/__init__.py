"""n8n template library integration.

This package lets OpenJarvis mirror the public n8n template library
(``api.n8n.io``), keep a lightweight catalog of every available workflow,
download full importable workflow JSON on demand, and *automatically* turn any
workflow added to the local library into a discoverable OpenJarvis managed-agent
template.

Public surface:

- :class:`~openjarvis.automations.n8n.client.N8nTemplateClient` — paginated API
  client over ``api.n8n.io``.
- :class:`~openjarvis.automations.n8n.catalog.Catalog` /
  :class:`~openjarvis.automations.n8n.catalog.CatalogEntry` — the on-disk index.
- :class:`~openjarvis.automations.n8n.sync.N8nLibrarySync` — sync the catalog and
  download full workflows into the library.
- :class:`~openjarvis.automations.n8n.installer.N8nAutoInstaller` — discover new
  library workflows and install them as agent templates (idempotent).
"""

from __future__ import annotations

from openjarvis.automations.n8n.catalog import Catalog, CatalogEntry
from openjarvis.automations.n8n.client import N8nTemplateClient
from openjarvis.automations.n8n.installer import N8nAutoInstaller
from openjarvis.automations.n8n.sync import N8nLibrarySync

__all__ = [
    "Catalog",
    "CatalogEntry",
    "N8nTemplateClient",
    "N8nAutoInstaller",
    "N8nLibrarySync",
]
