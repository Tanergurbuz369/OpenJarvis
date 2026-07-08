"""Tests for the keyword-based fleet dispatcher."""

from __future__ import annotations

import pytest

from openjarvis.fleet.dispatcher import FleetDispatcher, score_role
from openjarvis.fleet.registry import FleetRoleRegistry
from openjarvis.fleet.roles import FleetRole


@pytest.fixture()
def dispatcher(tmp_path):
    return FleetDispatcher(FleetRoleRegistry(custom_roles_dir=tmp_path))


class TestScoring:
    def test_phrase_keyword_outscores_token(self):
        role = FleetRole(
            role_id="x",
            name="X",
            category="c",
            icon="i",
            description="",
            keywords=["blog post"],
            system_prompt="p",
        )
        assert score_role("write a blog post", role) > 0
        assert score_role("completely unrelated", role) == 0

    def test_empty_task_scores_zero(self):
        role = FleetRole(
            role_id="x",
            name="X",
            category="c",
            icon="i",
            description="d",
            keywords=["k"],
            system_prompt="p",
        )
        assert score_role("", role) == 0.0


class TestDispatch:
    @pytest.mark.parametrize(
        ("task", "expected"),
        [
            ("write a blog post about local AI", "blog_writer"),
            ("plan a trip to Rome with a daily itinerary", "travel_planner"),
            ("analyze this csv of sales statistics", "data_analyst"),
            ("translate this document to Turkish", "translator"),
            ("design a workout plan for beginners", "fitness_coach"),
        ],
    )
    def test_picks_expected_specialist(self, dispatcher, task, expected):
        assert dispatcher.select(task).role_id == expected

    def test_rank_returns_scored_matches(self, dispatcher):
        matches = dispatcher.rank("research the market for electric bikes", top_k=3)
        assert 1 <= len(matches) <= 3
        assert matches[0].score >= matches[-1].score
        assert all(m.score > 0 for m in matches)

    def test_meta_roles_never_ranked(self, dispatcher):
        matches = dispatcher.rank(
            "plan and synthesize a final report summary", top_k=50
        )
        ids = {m.role.role_id for m in matches}
        assert "mission_planner" not in ids
        assert "chief_of_staff" not in ids

    def test_fallback_for_gibberish(self, dispatcher):
        role = dispatcher.select("zzqqxx yyzz")
        assert role.role_id == "web_researcher"
