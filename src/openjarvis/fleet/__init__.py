"""OpenJarvis Fleet — automatic multi-agent orchestration.

A large catalog of specialist agent *roles* (software, research, marketing,
finance, operations, personal assistance, ...) that are activated on demand:
give the fleet an objective, the mission planner decomposes it, the dispatcher
assigns each subtask to the best-suited specialist, subtasks execute in
parallel dependency stages, and the chief of staff synthesizes the final
deliverable. Everything runs on the local engine by default.
"""

from openjarvis.fleet.coordinator import FleetCoordinator
from openjarvis.fleet.dispatcher import FleetDispatcher, RoleMatch, score_role
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
from openjarvis.fleet.roles import BUILTIN_ROLES, FleetRole, builtin_roles
from openjarvis.fleet.specialist import FleetSpecialistAgent

__all__ = [
    "BUILTIN_ROLES",
    "FleetCoordinator",
    "FleetDispatcher",
    "FleetRole",
    "FleetRoleRegistry",
    "FleetSpecialistAgent",
    "Mission",
    "MissionStatus",
    "MissionStore",
    "RoleMatch",
    "Subtask",
    "SubtaskStatus",
    "builtin_roles",
    "new_mission",
    "new_subtask",
    "score_role",
]
