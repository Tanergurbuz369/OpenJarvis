"""Mission and subtask data model + in-memory store for the fleet."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MissionStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class Subtask:
    """One unit of work assigned to a single specialist agent."""

    subtask_id: str
    title: str
    description: str
    role_id: str
    depends_on: List[str] = field(default_factory=list)
    status: SubtaskStatus = SubtaskStatus.PENDING
    output: str = ""
    error: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "title": self.title,
            "description": self.description,
            "role_id": self.role_id,
            "depends_on": list(self.depends_on),
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tokens": self.tokens,
        }


@dataclass(slots=True)
class Mission:
    """A user objective executed by a team of specialist agents."""

    mission_id: str
    objective: str
    status: MissionStatus = MissionStatus.PENDING
    subtasks: List[Subtask] = field(default_factory=list)
    final_output: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    cancel_requested: bool = False

    def get_subtask(self, subtask_id: str) -> Optional[Subtask]:
        for st in self.subtasks:
            if st.subtask_id == subtask_id:
                return st
        return None

    def active_roles(self) -> List[str]:
        return [
            st.role_id for st in self.subtasks if st.status == SubtaskStatus.RUNNING
        ]

    def to_dict(self, *, include_subtasks: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "mission_id": self.mission_id,
            "objective": self.objective,
            "status": self.status.value,
            "final_output": self.final_output,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "subtask_count": len(self.subtasks),
            "active_roles": self.active_roles(),
        }
        if include_subtasks:
            data["subtasks"] = [st.to_dict() for st in self.subtasks]
        return data


def new_mission(objective: str) -> Mission:
    return Mission(mission_id=uuid.uuid4().hex[:12], objective=objective)


def new_subtask(
    title: str,
    description: str,
    role_id: str,
    depends_on: Optional[List[str]] = None,
) -> Subtask:
    return Subtask(
        subtask_id=uuid.uuid4().hex[:8],
        title=title,
        description=description,
        role_id=role_id,
        depends_on=list(depends_on or []),
    )


class MissionStore:
    """Thread-safe in-memory mission store (newest first)."""

    def __init__(self, *, max_missions: int = 200) -> None:
        self._missions: Dict[str, Mission] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._max = max_missions

    def add(self, mission: Mission) -> None:
        with self._lock:
            self._missions[mission.mission_id] = mission
            self._order.insert(0, mission.mission_id)
            while len(self._order) > self._max:
                stale = self._order.pop()
                self._missions.pop(stale, None)

    def get(self, mission_id: str) -> Optional[Mission]:
        with self._lock:
            return self._missions.get(mission_id)

    def list(self, *, limit: int = 50) -> List[Mission]:
        with self._lock:
            return [self._missions[mid] for mid in self._order[:limit]]

    def __len__(self) -> int:
        with self._lock:
            return len(self._order)


__all__ = [
    "Mission",
    "MissionStatus",
    "MissionStore",
    "Subtask",
    "SubtaskStatus",
    "new_mission",
    "new_subtask",
]
