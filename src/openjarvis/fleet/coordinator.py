"""Fleet coordinator: plans a mission, activates specialist agents, and
executes subtasks in parallel dependency stages.

Flow for one mission::

    objective ──► plan (LLM, dispatcher fallback)
              ──► stages of subtasks (dependency-ordered)
              ──► each subtask: activate the role's agent and run it
              ──► synthesize final deliverable (chief_of_staff)

Every state change is published on the :class:`~openjarvis.core.events.EventBus`
(``FLEET_*`` events) so the desktop UI can show agents coming online, working,
and finishing in real time.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from openjarvis.core.events import EventBus, EventType, get_event_bus
from openjarvis.fleet.dispatcher import FleetDispatcher
from openjarvis.fleet.mission import (
    Mission,
    MissionStatus,
    MissionStore,
    Subtask,
    SubtaskStatus,
    new_mission,
    new_subtask,
)
from openjarvis.fleet.registry import FleetRoleRegistry
from openjarvis.fleet.roles import FleetRole

logger = logging.getLogger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")

_PLANNER_PROMPT = """You are the mission planner for a fleet of specialist AI agents.
Decompose the objective below into 1-{max_subtasks} concrete subtasks.

Rules:
- Each subtask must be self-contained and produce a concrete deliverable.
- Assign each subtask the single best-suited specialist from the roster.
- Use "depends_on" (list of earlier subtask indices, 0-based) only when a
  subtask genuinely needs another's output; independent subtasks run in parallel.
- Reply with ONLY a JSON array, no prose. Schema:
  [{{"title": "...", "description": "...", "role": "<role_id>", "depends_on": [0]}}]

Specialist roster (role_id: description):
{roster}

Objective:
{objective}"""

_SYNTHESIS_PROMPT = """Mission objective:
{objective}

Below are the outputs of the specialist agents that worked on this mission.
Merge them into one final, well-structured deliverable that fully answers the
objective. Resolve contradictions and remove duplication.

{sections}"""


class FleetCoordinator:
    """Plans and executes missions across the specialist fleet."""

    def __init__(
        self,
        engine: Any,
        model: str,
        *,
        registry: Optional[FleetRoleRegistry] = None,
        dispatcher: Optional[FleetDispatcher] = None,
        store: Optional[MissionStore] = None,
        bus: Optional[EventBus] = None,
        max_parallel: int = 4,
        max_subtasks: int = 8,
        agent_factory: Optional[Callable[[FleetRole, Any, str], Any]] = None,
    ) -> None:
        self._engine = engine
        self._model = model
        self.registry = registry or FleetRoleRegistry()
        self.dispatcher = dispatcher or FleetDispatcher(self.registry)
        self.store = store or MissionStore()
        self._bus = bus or get_event_bus()
        self._max_parallel = max(1, max_parallel)
        self._max_subtasks = max(1, max_subtasks)
        self._agent_factory = agent_factory or self._default_agent_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, objective: str) -> Mission:
        """Create a mission and start executing it on a background thread."""
        mission = new_mission(objective)
        self.store.add(mission)
        thread = threading.Thread(
            target=self._safe_run,
            args=(mission,),
            daemon=True,
            name=f"fleet-mission-{mission.mission_id}",
        )
        thread.start()
        return mission

    def run_mission_sync(self, objective: str) -> Mission:
        """Create a mission and run it to completion on this thread."""
        mission = new_mission(objective)
        self.store.add(mission)
        self._safe_run(mission)
        return mission

    def cancel(self, mission_id: str) -> bool:
        mission = self.store.get(mission_id)
        if mission is None:
            return False
        mission.cancel_requested = True
        return True

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan(self, objective: str) -> List[Subtask]:
        """Decompose *objective* into role-assigned subtasks.

        Uses the LLM planner when an engine is available and falls back to a
        single dispatcher-selected subtask otherwise.
        """
        raw_plan = self._llm_plan(objective) if self._engine is not None else None
        if raw_plan:
            subtasks = self._materialize_plan(raw_plan, objective)
            if subtasks:
                return subtasks
        # Fallback: one subtask, best-matching specialist.
        role = self.dispatcher.select(objective)
        return [new_subtask(objective[:80] or "Task", objective, role.role_id)]

    def _llm_plan(self, objective: str) -> Optional[List[Dict[str, Any]]]:
        roster = "\n".join(
            f"- {r.role_id}: {r.description}"
            for r in self.registry.all()
            if r.role_id not in ("mission_planner", "chief_of_staff")
        )
        prompt = _PLANNER_PROMPT.format(
            max_subtasks=self._max_subtasks, roster=roster, objective=objective
        )
        try:
            content = self._ask_role("mission_planner", prompt)
        except Exception as exc:
            logger.warning("Fleet planner LLM call failed: %s", exc)
            return None
        return self._parse_plan_json(content)

    @staticmethod
    def _parse_plan_json(content: str) -> Optional[List[Dict[str, Any]]]:
        if not content:
            return None
        match = _JSON_ARRAY_RE.search(content)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list):
            return None
        return [item for item in data if isinstance(item, dict)]

    def _materialize_plan(
        self, raw_plan: List[Dict[str, Any]], objective: str
    ) -> List[Subtask]:
        entries = raw_plan[: self._max_subtasks]
        subtasks: List[Subtask] = []
        for entry in entries:
            description = str(entry.get("description") or entry.get("title") or "")
            if not description.strip():
                continue
            title = str(entry.get("title") or description[:60])
            role_id = str(entry.get("role") or entry.get("role_id") or "")
            if role_id not in self.registry:
                role_id = self.dispatcher.select(f"{title} {description}").role_id
            subtasks.append(new_subtask(title, description, role_id))
        # Second pass: resolve depends_on indices to subtask ids.
        for entry, subtask in zip(entries, subtasks):
            deps = entry.get("depends_on") or []
            if not isinstance(deps, list):
                continue
            for dep in deps:
                if isinstance(dep, (int, float)):
                    idx = int(dep)
                    if 0 <= idx < len(subtasks):
                        dep_id = subtasks[idx].subtask_id
                        if dep_id != subtask.subtask_id:
                            subtask.depends_on.append(dep_id)
        return subtasks

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _safe_run(self, mission: Mission) -> None:
        try:
            self._run(mission)
        except Exception as exc:  # Never let a mission thread die silently
            logger.exception("Fleet mission %s crashed", mission.mission_id)
            mission.status = MissionStatus.FAILED
            mission.error = str(exc)
            self._publish(EventType.FLEET_MISSION_END, mission)

    def _run(self, mission: Mission) -> None:
        import time as _time

        mission.status = MissionStatus.PLANNING
        mission.started_at = _time.time()
        self._publish(EventType.FLEET_MISSION_START, mission)

        mission.subtasks = self.plan(mission.objective)
        mission.status = MissionStatus.RUNNING
        self._publish(EventType.FLEET_MISSION_PLANNED, mission)

        for stage in self._stages(mission.subtasks):
            if mission.cancel_requested:
                break
            runnable = [st for st in stage if st.status == SubtaskStatus.PENDING]
            if len(runnable) == 1:
                self._run_subtask(mission, runnable[0])
            elif runnable:
                with ThreadPoolExecutor(
                    max_workers=min(self._max_parallel, len(runnable))
                ) as pool:
                    futures = [
                        pool.submit(self._run_subtask, mission, st) for st in runnable
                    ]
                    for fut in futures:
                        fut.result()

        if mission.cancel_requested:
            mission.status = MissionStatus.CANCELED
            for st in mission.subtasks:
                if st.status == SubtaskStatus.PENDING:
                    st.status = SubtaskStatus.SKIPPED
        else:
            mission.final_output = self._synthesize(mission)
            failed = [
                st for st in mission.subtasks if st.status == SubtaskStatus.FAILED
            ]
            mission.status = (
                MissionStatus.FAILED
                if failed and len(failed) == len(mission.subtasks)
                else MissionStatus.COMPLETED
            )
        mission.finished_at = _time.time()
        self._publish(EventType.FLEET_MISSION_END, mission)

    def _stages(self, subtasks: List[Subtask]) -> List[List[Subtask]]:
        """Order subtasks into parallel stages honoring ``depends_on``."""
        remaining = list(subtasks)
        done_ids: set[str] = set()
        stages: List[List[Subtask]] = []
        while remaining:
            ready = [
                st for st in remaining if all(dep in done_ids for dep in st.depends_on)
            ]
            if not ready:
                # Dependency cycle or dangling reference — run the rest
                # together rather than deadlocking.
                ready = remaining
            stages.append(ready)
            done_ids.update(st.subtask_id for st in ready)
            remaining = [st for st in remaining if st not in ready]
        return stages

    def _run_subtask(self, mission: Mission, subtask: Subtask) -> None:
        import time as _time

        if mission.cancel_requested:
            subtask.status = SubtaskStatus.SKIPPED
            return

        role = self.registry.get(subtask.role_id) or self.dispatcher.select(
            subtask.description
        )
        subtask.status = SubtaskStatus.RUNNING
        subtask.started_at = _time.time()
        self._publish(EventType.FLEET_TASK_START, mission, subtask, role)

        input_text = self._subtask_input(mission, subtask)
        try:
            agent = self._agent_factory(role, self._engine, self._model)
            result = agent.run(input_text)
            subtask.output = getattr(result, "content", "") or ""
            usage = (getattr(result, "metadata", None) or {}).get("usage") or {}
            subtask.tokens = int(usage.get("total_tokens") or 0)
            subtask.status = SubtaskStatus.COMPLETED
        except Exception as exc:
            logger.warning(
                "Fleet subtask %s (%s) failed: %s",
                subtask.subtask_id,
                role.role_id,
                exc,
            )
            subtask.error = str(exc)
            subtask.status = SubtaskStatus.FAILED
        subtask.finished_at = _time.time()
        self._publish(EventType.FLEET_TASK_END, mission, subtask, role)

    def _subtask_input(self, mission: Mission, subtask: Subtask) -> str:
        parts = [
            f"Mission objective: {mission.objective}",
            f"Your subtask: {subtask.title}",
            subtask.description,
        ]
        dep_outputs = []
        for dep_id in subtask.depends_on:
            dep = mission.get_subtask(dep_id)
            if dep and dep.output:
                dep_outputs.append(f"### Output of '{dep.title}'\n{dep.output}")
        if dep_outputs:
            parts.append(
                "Context from teammates who worked before you:\n"
                + "\n\n".join(dep_outputs)
            )
        return "\n\n".join(parts)

    def _synthesize(self, mission: Mission) -> str:
        completed = [
            st
            for st in mission.subtasks
            if st.status == SubtaskStatus.COMPLETED and st.output
        ]
        if not completed:
            return ""
        if len(completed) == 1:
            return completed[0].output
        sections = "\n\n".join(
            f"## {st.title} (by {st.role_id})\n{st.output}" for st in completed
        )
        prompt = _SYNTHESIS_PROMPT.format(
            objective=mission.objective, sections=sections
        )
        try:
            return self._ask_role("chief_of_staff", prompt)
        except Exception as exc:
            logger.warning("Fleet synthesis failed, concatenating outputs: %s", exc)
            return sections

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _ask_role(self, role_id: str, prompt: str) -> str:
        role = self.registry.get(role_id)
        system_prompt = role.system_prompt if role else ""
        from openjarvis.fleet.specialist import FleetSpecialistAgent

        agent = FleetSpecialistAgent(
            self._engine, self._model, system_prompt=system_prompt, bus=self._bus
        )
        return agent.run(prompt).content

    def _default_agent_factory(self, role: FleetRole, engine: Any, model: str) -> Any:
        system_prompt = (
            f"You are {role.name}, a specialist agent in the OpenJarvis fleet. "
            "You receive one subtask of a larger mission. Deliver concrete, "
            "actionable output for your subtask only; teammates handle the rest.\n\n"
            + role.system_prompt
        )
        tools = self._resolve_tools(role.tools)
        if tools:
            try:
                from openjarvis.agents.orchestrator import OrchestratorAgent

                return OrchestratorAgent(
                    engine,
                    model,
                    tools=tools,
                    system_prompt=system_prompt,
                    bus=self._bus,
                )
            except Exception as exc:
                logger.warning(
                    "Falling back to tool-less specialist for %s: %s",
                    role.role_id,
                    exc,
                )
        from openjarvis.fleet.specialist import FleetSpecialistAgent

        return FleetSpecialistAgent(
            engine, model, system_prompt=system_prompt, bus=self._bus
        )

    @staticmethod
    def _resolve_tools(tool_names: List[str]) -> List[Any]:
        """Instantiate registered tools by name; unknown tools are skipped."""
        if not tool_names:
            return []
        try:
            from openjarvis.server.agent_manager_routes import (
                _ensure_registries_populated,
            )

            _ensure_registries_populated()
        except Exception:
            pass
        try:
            from openjarvis.core.registry import ToolRegistry
        except ImportError:
            return []
        instances = []
        for name in tool_names:
            if not ToolRegistry.contains(name):
                continue
            try:
                instances.append(ToolRegistry.get(name)())
            except Exception:
                logger.debug("Fleet could not instantiate tool %s", name)
        return instances

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _publish(
        self,
        event_type: EventType,
        mission: Mission,
        subtask: Optional[Subtask] = None,
        role: Optional[FleetRole] = None,
    ) -> None:
        data: Dict[str, Any] = {
            "mission_id": mission.mission_id,
            "objective": mission.objective,
            "mission_status": mission.status.value,
            "subtask_count": len(mission.subtasks),
            "active_roles": mission.active_roles(),
        }
        if subtask is not None:
            data.update(
                {
                    "subtask_id": subtask.subtask_id,
                    "subtask_title": subtask.title,
                    "subtask_status": subtask.status.value,
                    "role_id": subtask.role_id,
                    "error": subtask.error,
                }
            )
        if role is not None:
            data.update({"role_name": role.name, "role_icon": role.icon})
        try:
            self._bus.publish(event_type, data)
        except Exception:
            logger.debug("Fleet event publish failed", exc_info=True)


__all__ = ["FleetCoordinator"]
