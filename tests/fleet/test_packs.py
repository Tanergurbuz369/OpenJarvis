"""Tests for the tailored fleet role packs."""

from __future__ import annotations

from openjarvis.fleet.dispatcher import FleetDispatcher
from openjarvis.fleet.packs import PACK_ROLES
from openjarvis.fleet.registry import FleetRoleRegistry
from openjarvis.fleet.roles import BUILTIN_ROLES


class TestPackCatalog:
    def test_pack_size_and_categories(self):
        assert len(PACK_ROLES) >= 20
        categories = {r.category for r in PACK_ROLES}
        assert {"ecommerce", "content", "personal", "turkish"} <= categories

    def test_no_id_collisions_with_builtins(self):
        all_ids = [r.role_id for r in [*BUILTIN_ROLES, *PACK_ROLES]]
        assert len(all_ids) == len(set(all_ids))

    def test_every_pack_role_is_complete(self):
        for role in PACK_ROLES:
            assert role.role_id and role.name and role.description
            assert role.system_prompt
            assert role.keywords, f"{role.role_id} has no keywords"


class TestPackDispatch:
    def test_registry_includes_packs(self, tmp_path):
        reg = FleetRoleRegistry(custom_roles_dir=tmp_path)
        assert "etsy_listing_writer" in reg
        assert "turkce_metin_yazari" in reg
        assert "ecommerce" in reg.categories()

    def test_turkish_keywords_match(self, tmp_path):
        d = FleetDispatcher(FleetRoleRegistry(custom_roles_dir=tmp_path))
        assert d.select("bir dilekçe yazar mısın").role_id == "resmi_yazisma_uzmani"
        assert d.select("etsy listing için ürün açıklaması yaz").role_id == (
            "etsy_listing_writer"
        )

    def test_english_keywords_still_match(self, tmp_path):
        d = FleetDispatcher(FleetRoleRegistry(custom_roles_dir=tmp_path))
        assert d.select("plan my week with time blocking").role_id == "weekly_planner"
