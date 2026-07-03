"""Fleet role registry: built-in catalog + user-defined roles.

Custom roles live as TOML files in ``~/.openjarvis/fleet/roles/*.toml``::

    [role]
    role_id = "wine_sommelier"
    name = "Wine Sommelier"
    category = "personal"
    icon = "🍷"
    description = "Recommends wine pairings."
    keywords = ["wine", "pairing", "sommelier"]
    system_prompt = "You are an expert sommelier..."
    tools = ["web_search"]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from openjarvis.fleet.roles import FleetRole, builtin_roles

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

DEFAULT_CUSTOM_ROLES_DIR = Path.home() / ".openjarvis" / "fleet" / "roles"


class FleetRoleRegistry:
    """Holds every role the fleet can activate."""

    def __init__(self, *, custom_roles_dir: Optional[Path] = None) -> None:
        self._roles: Dict[str, FleetRole] = {}
        for role in builtin_roles():
            self._roles[role.role_id] = role
        self._custom_dir = (
            Path(custom_roles_dir) if custom_roles_dir else DEFAULT_CUSTOM_ROLES_DIR
        )
        self._load_custom_roles()

    # -- loading -------------------------------------------------------------

    def _load_custom_roles(self) -> None:
        if not self._custom_dir.is_dir():
            return
        for path in sorted(self._custom_dir.glob("*.toml")):
            try:
                with open(path, "rb") as fh:
                    data = tomllib.load(fh)
                section = data.get("role", data)
                role = FleetRole(
                    role_id=str(section["role_id"]),
                    name=str(section.get("name", section["role_id"])),
                    category=str(section.get("category", "custom")),
                    icon=str(section.get("icon", "🧩")),
                    description=str(section.get("description", "")),
                    keywords=[str(k) for k in section.get("keywords", [])],
                    system_prompt=str(section.get("system_prompt", "")),
                    tools=[str(t) for t in section.get("tools", [])],
                    builtin=False,
                )
                self._roles[role.role_id] = role
            except Exception as exc:
                logger.warning("Skipping invalid fleet role file %s: %s", path, exc)

    # -- queries --------------------------------------------------------------

    def get(self, role_id: str) -> Optional[FleetRole]:
        return self._roles.get(role_id)

    def all(self) -> List[FleetRole]:
        return list(self._roles.values())

    def __len__(self) -> int:
        return len(self._roles)

    def __contains__(self, role_id: str) -> bool:
        return role_id in self._roles

    def categories(self) -> List[str]:
        seen: List[str] = []
        for role in self._roles.values():
            if role.category not in seen:
                seen.append(role.category)
        return seen

    def by_category(self, category: str) -> List[FleetRole]:
        return [r for r in self._roles.values() if r.category == category]

    def search(self, query: str) -> List[FleetRole]:
        """Case-insensitive substring search over id, name, and keywords."""
        q = query.strip().lower()
        if not q:
            return self.all()
        hits = []
        for role in self._roles.values():
            haystack = " ".join(
                [role.role_id, role.name, role.description, *role.keywords]
            ).lower()
            if q in haystack:
                hits.append(role)
        return hits

    def add(self, role: FleetRole) -> None:
        """Register a role programmatically (overwrites same role_id)."""
        self._roles[role.role_id] = role


__all__ = ["FleetRoleRegistry", "DEFAULT_CUSTOM_ROLES_DIR"]
