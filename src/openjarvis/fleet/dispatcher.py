"""Fleet dispatcher: picks the right specialist role(s) for a task.

The dispatcher is deliberately LLM-free so it costs nothing and works even
when no engine is loaded. It scores every role in the registry against the
task text using keyword and name matches; the coordinator's LLM planner can
override these picks when it produces an explicit plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from openjarvis.fleet.registry import FleetRoleRegistry
from openjarvis.fleet.roles import FleetRole

# \w keeps non-ASCII letters so Turkish keywords (ürün, dilekçe, ...) tokenize.
_WORD_RE = re.compile(r"[\w']+")

# Roles never auto-picked by scoring — they are meta roles the coordinator
# invokes explicitly (planning and synthesis).
_META_ROLES = {"mission_planner", "chief_of_staff"}


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())


@dataclass(slots=True)
class RoleMatch:
    role: FleetRole
    score: float

    def to_dict(self) -> dict:
        return {"role": self.role.to_dict(), "score": round(self.score, 3)}


def score_role(task: str, role: FleetRole) -> float:
    """Score how well *role* fits *task* (higher is better, 0 = no match)."""
    task_lower = task.lower()
    task_tokens = set(_tokens(task))
    if not task_tokens:
        return 0.0

    score = 0.0
    # Multi-word keywords match as phrases; single words as tokens.
    for kw in role.keywords:
        kw_lower = kw.lower()
        if " " in kw_lower:
            if kw_lower in task_lower:
                score += 3.0
        elif kw_lower in task_tokens:
            score += 2.0

    # Name and description token overlap as a weak signal.
    name_tokens = set(_tokens(role.name))
    score += 1.0 * len(task_tokens & name_tokens)
    desc_tokens = set(_tokens(role.description))
    score += 0.25 * len(task_tokens & desc_tokens)
    return score


class FleetDispatcher:
    """Selects the best specialist roles for a given task description."""

    def __init__(self, registry: FleetRoleRegistry) -> None:
        self._registry = registry

    def rank(self, task: str, *, top_k: int = 5) -> List[RoleMatch]:
        """Return the top-*k* roles ranked by match score (score > 0 only)."""
        matches = [
            RoleMatch(role=role, score=score_role(task, role))
            for role in self._registry.all()
            if role.role_id not in _META_ROLES
        ]
        matches = [m for m in matches if m.score > 0]
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]

    def select(self, task: str, *, fallback: str = "web_researcher") -> FleetRole:
        """Return the single best role, falling back to a generalist."""
        ranked = self.rank(task, top_k=1)
        if ranked:
            return ranked[0].role
        role = self._registry.get(fallback)
        if role is not None:
            return role
        # Registry may have been emptied/customized — take anything non-meta.
        for candidate in self._registry.all():
            if candidate.role_id not in _META_ROLES:
                return candidate
        raise LookupError("Fleet role registry is empty")


__all__ = ["FleetDispatcher", "RoleMatch", "score_role"]
