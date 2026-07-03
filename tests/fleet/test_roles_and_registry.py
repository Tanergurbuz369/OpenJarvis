"""Tests for the fleet role catalog and registry."""

from __future__ import annotations

from pathlib import Path

from openjarvis.fleet.registry import FleetRoleRegistry
from openjarvis.fleet.roles import BUILTIN_ROLES


class TestBuiltinCatalog:
    def test_catalog_is_large(self):
        assert len(BUILTIN_ROLES) >= 90

    def test_role_ids_unique(self):
        ids = [r.role_id for r in BUILTIN_ROLES]
        assert len(ids) == len(set(ids))

    def test_every_role_is_complete(self):
        for role in BUILTIN_ROLES:
            assert role.role_id
            assert role.name
            assert role.category
            assert role.description
            assert role.system_prompt
            assert role.keywords, f"{role.role_id} has no keywords"

    def test_meta_roles_exist(self):
        ids = {r.role_id for r in BUILTIN_ROLES}
        assert "mission_planner" in ids
        assert "chief_of_staff" in ids

    def test_to_dict_round_trip(self):
        d = BUILTIN_ROLES[0].to_dict()
        assert d["role_id"] == BUILTIN_ROLES[0].role_id
        assert isinstance(d["keywords"], list)


class TestRegistry:
    def test_loads_builtins(self, tmp_path: Path):
        reg = FleetRoleRegistry(custom_roles_dir=tmp_path)
        assert len(reg) == len(BUILTIN_ROLES)
        assert "web_researcher" in reg

    def test_custom_role_from_toml(self, tmp_path: Path):
        (tmp_path / "sommelier.toml").write_text(
            """
[role]
role_id = "wine_sommelier"
name = "Wine Sommelier"
category = "personal"
icon = "🍷"
description = "Recommends wine pairings."
keywords = ["wine", "pairing"]
system_prompt = "You are an expert sommelier."
tools = ["web_search"]
""",
            encoding="utf-8",
        )
        reg = FleetRoleRegistry(custom_roles_dir=tmp_path)
        role = reg.get("wine_sommelier")
        assert role is not None
        assert role.builtin is False
        assert role.tools == ["web_search"]

    def test_invalid_toml_is_skipped(self, tmp_path: Path):
        (tmp_path / "broken.toml").write_text("not [ valid", encoding="utf-8")
        reg = FleetRoleRegistry(custom_roles_dir=tmp_path)
        assert len(reg) == len(BUILTIN_ROLES)

    def test_search(self, tmp_path: Path):
        reg = FleetRoleRegistry(custom_roles_dir=tmp_path)
        hits = reg.search("wine")
        assert all("wine" not in r.role_id for r in hits) or hits == []
        hits = reg.search("travel")
        assert any(r.role_id == "travel_planner" for r in hits)

    def test_by_category_and_categories(self, tmp_path: Path):
        reg = FleetRoleRegistry(custom_roles_dir=tmp_path)
        assert "engineering" in reg.categories()
        eng = reg.by_category("engineering")
        assert eng and all(r.category == "engineering" for r in eng)
