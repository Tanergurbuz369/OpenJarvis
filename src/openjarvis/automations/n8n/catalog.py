"""On-disk catalog of n8n template-library workflows.

The catalog is a lightweight index — one small record per workflow — so the
repository can track *every* available workflow (10k+) without committing the
full workflow JSON for each. Full workflow JSON is downloaded on demand into the
library directory (see :mod:`openjarvis.automations.n8n.sync`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _truncate(text: str, max_len: int = 200) -> str:
    """Trim *text* to *max_len* chars on a word boundary with an ellipsis."""
    text = (text or "").strip().replace("\n", " ").replace("\r", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0].rstrip() + "…"


def _slugify(text: str, max_len: int = 60) -> str:
    """Return a filesystem-safe slug for *text*."""
    out: List[str] = []
    for ch in (text or "").lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug[:max_len] or "workflow"


@dataclass(slots=True)
class CatalogEntry:
    """A single workflow's metadata within the catalog."""

    id: int
    name: str
    slug: str = ""
    description: str = ""
    author: str = ""
    categories: List[str] = field(default_factory=list)
    nodes: int = 0
    total_views: int = 0
    url: str = ""
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = _slugify(self.name)
        if not self.url:
            self.url = f"https://n8n.io/workflows/{self.id}/"

    @classmethod
    def from_api(cls, wf: Dict[str, Any]) -> "CatalogEntry":
        """Build an entry from an ``api.n8n.io`` workflow list/detail object."""
        user = wf.get("user") or {}
        categories = [
            c.get("name", "")
            for c in (wf.get("categories") or [])
            if isinstance(c, dict) and c.get("name")
        ]
        nodes = wf.get("nodes")
        node_count = len(nodes) if isinstance(nodes, list) else int(nodes or 0)
        return cls(
            id=int(wf["id"]),
            name=wf.get("name") or "Untitled workflow",
            description=_truncate(wf.get("description") or ""),
            author=user.get("name") or user.get("username") or "",
            categories=categories,
            nodes=node_count,
            total_views=int(wf.get("totalViews") or 0),
            created_at=wf.get("createdAt"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "author": self.author,
            "categories": self.categories,
            "nodes": self.nodes,
            "total_views": self.total_views,
            "url": self.url,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CatalogEntry":
        return cls(
            id=int(data["id"]),
            name=data.get("name", ""),
            slug=data.get("slug", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            categories=list(data.get("categories", [])),
            nodes=int(data.get("nodes", 0)),
            total_views=int(data.get("total_views", 0)),
            url=data.get("url", ""),
            created_at=data.get("created_at"),
        )

    def library_filename(self) -> str:
        """Deterministic filename used when this workflow is downloaded."""
        return f"{self.id}-{self.slug}.workflow.json"


@dataclass(slots=True)
class Catalog:
    """The full set of known workflows, keyed by id."""

    entries: Dict[int, CatalogEntry] = field(default_factory=dict)
    total_available: int = 0
    synced_at: Optional[str] = None

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, wid: int) -> bool:
        return int(wid) in self.entries

    def upsert(self, entry: CatalogEntry) -> None:
        self.entries[entry.id] = entry

    def sorted_entries(self) -> List[CatalogEntry]:
        """Entries sorted by popularity (most viewed first)."""
        return sorted(self.entries.values(), key=lambda e: e.total_views, reverse=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_available": self.total_available,
            "synced_at": self.synced_at,
            "count": len(self.entries),
            "workflows": [e.to_dict() for e in self.sorted_entries()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Catalog":
        entries = {
            int(w["id"]): CatalogEntry.from_dict(w) for w in data.get("workflows", [])
        }
        return cls(
            entries=entries,
            total_available=int(data.get("total_available", 0)),
            synced_at=data.get("synced_at"),
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
