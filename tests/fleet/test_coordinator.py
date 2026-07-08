"""Tests for the fleet coordinator (planning, staged execution, synthesis)."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from openjarvis.core.events import EventBus, EventType
from openjarvis.fleet.coordinator import FleetCoordinator
from openjarvis.fleet.mission import MissionStatus, SubtaskStatus, new_subtask
from openjarvis.fleet.registry import FleetRoleRegistry


class KeyedFakeEngine:
    """Thread-safe fake engine that answers based on prompt content.

    Fleet subtasks run in parallel threads, so an ordered-response fake
    (``tests/agents/fake_engine.FakeEngine``) would be nondeterministic here.
    """

    def __init__(self, plan: List[Dict[str, Any]] | None = None) -> None:
        self._plan = plan

    def generate(self, messages: list, *, model: str = "", **kw: Any) -> Dict[str, Any]:
        text = " ".join(
            str(getattr(m, "content", None) or m.get("content", ""))
            if isinstance(m, dict)
            else str(getattr(m, "content", ""))
            for m in messages or []
        )
        if "mission planner for a fleet" in text:
            content = (
                json.dumps(self._plan) if self._plan is not None else "no json here"
            )
        elif "Chief of Staff" in text:
            content = "SYNTHESIS"
        else:
            content = f"WORK[{text[:30]}]"
        return {"content": content, "usage": {"total_tokens": 7}}


@pytest.fixture()
def registry(tmp_path):
    return FleetRoleRegistry(custom_roles_dir=tmp_path)


def make_coordinator(registry, plan=None, **kwargs):
    bus = EventBus(record_history=True)
    engine = KeyedFakeEngine(plan)
    coord = FleetCoordinator(engine, "fake-model", registry=registry, bus=bus, **kwargs)
    return coord, bus


class TestPlanning:
    def test_llm_plan_materializes_subtasks(self, registry):
        plan = [
            {"title": "A", "description": "Research topic", "role": "web_researcher"},
            {
                "title": "B",
                "description": "Write article",
                "role": "blog_writer",
                "depends_on": [0],
            },
        ]
        coord, _ = make_coordinator(registry, plan)
        subtasks = coord.plan("write about X")
        assert [st.role_id for st in subtasks] == ["web_researcher", "blog_writer"]
        assert subtasks[1].depends_on == [subtasks[0].subtask_id]

    def test_unknown_role_falls_back_to_dispatcher(self, registry):
        plan = [
            {
                "title": "T",
                "description": "translate this text to Turkish",
                "role": "nonexistent_role",
            }
        ]
        coord, _ = make_coordinator(registry, plan)
        subtasks = coord.plan("translate")
        assert subtasks[0].role_id == "translator"

    def test_unparseable_plan_falls_back_to_single_subtask(self, registry):
        coord, _ = make_coordinator(registry, plan=None)
        subtasks = coord.plan("plan a trip to Rome itinerary")
        assert len(subtasks) == 1
        assert subtasks[0].role_id == "travel_planner"

    def test_plan_respects_max_subtasks(self, registry):
        plan = [
            {"title": f"T{i}", "description": f"task {i}", "role": "web_researcher"}
            for i in range(10)
        ]
        coord, _ = make_coordinator(registry, plan, max_subtasks=3)
        assert len(coord.plan("do many things")) == 3

    def test_parse_plan_json_extracts_embedded_array(self):
        content = 'Sure! Here is the plan:\n[{"title": "A", "description": "d"}]\nDone.'
        parsed = FleetCoordinator._parse_plan_json(content)
        assert parsed == [{"title": "A", "description": "d"}]
        assert FleetCoordinator._parse_plan_json("no json") is None
        assert FleetCoordinator._parse_plan_json('{"not": "array"}') is None


class TestStages:
    def test_dependency_stages(self, registry):
        coord, _ = make_coordinator(registry)
        a = new_subtask("a", "a", "web_researcher")
        b = new_subtask("b", "b", "blog_writer", depends_on=[a.subtask_id])
        c = new_subtask("c", "c", "data_analyst")
        stages = coord._stages([a, b, c])
        titles = [sorted(st.title for st in stage) for stage in stages]
        assert titles == [["a", "c"], ["b"]]

    def test_cycle_does_not_deadlock(self, registry):
        coord, _ = make_coordinator(registry)
        a = new_subtask("a", "a", "web_researcher")
        b = new_subtask("b", "b", "blog_writer")
        a.depends_on.append(b.subtask_id)
        b.depends_on.append(a.subtask_id)
        stages = coord._stages([a, b])
        assert sum(len(s) for s in stages) == 2


class TestExecution:
    def test_mission_runs_to_completion_with_synthesis(self, registry):
        plan = [
            {"title": "Research", "description": "Research", "role": "tutor"},
            {
                "title": "Write",
                "description": "Write",
                "role": "blog_writer",
                "depends_on": [0],
            },
        ]
        coord, bus = make_coordinator(registry, plan)
        mission = coord.run_mission_sync("write about local AI")

        assert mission.status == MissionStatus.COMPLETED
        assert all(st.status == SubtaskStatus.COMPLETED for st in mission.subtasks)
        assert all(st.output.startswith("WORK[") for st in mission.subtasks)
        assert mission.final_output == "SYNTHESIS"

        types = [e.event_type for e in bus.history]
        assert types[0] == EventType.FLEET_MISSION_START
        assert types[-1] == EventType.FLEET_MISSION_END
        assert types.count(EventType.FLEET_TASK_START) == 2
        assert types.count(EventType.FLEET_TASK_END) == 2

    def test_single_subtask_skips_synthesis(self, registry):
        plan = [{"title": "Solo", "description": "explain X", "role": "tutor"}]
        coord, _ = make_coordinator(registry, plan)
        mission = coord.run_mission_sync("explain X")
        assert mission.status == MissionStatus.COMPLETED
        assert mission.final_output == mission.subtasks[0].output

    def test_dependent_subtask_sees_upstream_output(self, registry):
        plan = [
            {"title": "First", "description": "produce data", "role": "tutor"},
            {
                "title": "Second",
                "description": "use data",
                "role": "blog_writer",
                "depends_on": [0],
            },
        ]
        coord, _ = make_coordinator(registry, plan)
        mission = coord.run_mission_sync("two step")
        second = mission.subtasks[1]
        text = coord._subtask_input(mission, second)
        assert "Output of 'First'" in text

    def test_failing_agent_marks_subtask_failed(self, registry):
        class ExplodingEngine:
            def generate(self, messages, **kw):
                text = " ".join(str(getattr(m, "content", "")) for m in messages)
                if "mission planner" in text:
                    plan = '[{"title": "T", "description": "d", "role": "tutor"}]'
                    return {"content": plan, "usage": {}}
                raise RuntimeError("boom")

        bus = EventBus()
        coord = FleetCoordinator(ExplodingEngine(), "fake", registry=registry, bus=bus)
        mission = coord.run_mission_sync("do it")
        assert mission.subtasks[0].status == SubtaskStatus.FAILED
        assert "boom" in mission.subtasks[0].error
        # All subtasks failed -> mission failed
        assert mission.status == MissionStatus.FAILED

    def test_cancel_skips_pending_subtasks(self, registry):
        plan = [{"title": "T", "description": "d", "role": "tutor"}]
        coord, _ = make_coordinator(registry, plan)
        mission = coord.run_mission_sync("x")  # completes normally
        assert coord.cancel(mission.mission_id) is True
        assert coord.cancel("does-not-exist") is False

    def test_store_tracks_missions(self, registry):
        coord, _ = make_coordinator(
            registry, [{"title": "T", "description": "d", "role": "tutor"}]
        )
        mission = coord.run_mission_sync("x")
        assert coord.store.get(mission.mission_id) is mission
        assert coord.store.list()[0] is mission
