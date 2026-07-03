"""REST API for the fleet multi-agent orchestration subsystem."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from openjarvis.fleet import FleetCoordinator
from openjarvis.fleet.mission import MissionStatus

logger = logging.getLogger(__name__)

fleet_router = APIRouter(prefix="/v1/fleet", tags=["fleet"])


class CreateMissionRequest(BaseModel):
    objective: str = Field(
        ..., min_length=1, description="What the fleet should accomplish"
    )
    max_subtasks: Optional[int] = Field(None, ge=1, le=20)
    max_parallel: Optional[int] = Field(None, ge=1, le=16)


def _get_coordinator(request: Request) -> FleetCoordinator:
    """Return the app-wide coordinator, creating it lazily from app state."""
    state = request.app.state
    coordinator = getattr(state, "fleet_coordinator", None)
    if coordinator is None:
        engine = getattr(state, "engine", None)
        model = getattr(state, "model", "") or ""
        bus = getattr(state, "bus", None)
        coordinator = FleetCoordinator(engine, model, bus=bus)
        state.fleet_coordinator = coordinator
    return coordinator


@fleet_router.get("/status")
async def fleet_status(request: Request):
    coordinator = _get_coordinator(request)
    missions = coordinator.store.list(limit=200)
    active = [
        m
        for m in missions
        if m.status in (MissionStatus.PLANNING, MissionStatus.RUNNING)
    ]
    active_roles = [rid for m in active for rid in m.active_roles()]
    return {
        "roles": len(coordinator.registry),
        "categories": coordinator.registry.categories(),
        "missions_total": len(missions),
        "missions_active": len(active),
        "active_roles": active_roles,
    }


@fleet_router.get("/roles")
async def list_roles(request: Request, q: str = "", category: str = ""):
    coordinator = _get_coordinator(request)
    roles = coordinator.registry.search(q) if q else coordinator.registry.all()
    if category:
        roles = [r for r in roles if r.category == category]
    return {"roles": [r.to_dict() for r in roles]}


@fleet_router.get("/roles/match")
async def match_roles(request: Request, task: str, top_k: int = 5):
    """Preview which specialists the dispatcher would pick for a task."""
    coordinator = _get_coordinator(request)
    matches = coordinator.dispatcher.rank(task, top_k=max(1, min(top_k, 20)))
    return {"matches": [m.to_dict() for m in matches]}


@fleet_router.get("/missions")
async def list_missions(request: Request, limit: int = 50):
    coordinator = _get_coordinator(request)
    missions = coordinator.store.list(limit=max(1, min(limit, 200)))
    return {"missions": [m.to_dict(include_subtasks=False) for m in missions]}


@fleet_router.post("/missions")
async def create_mission(req: CreateMissionRequest, request: Request):
    coordinator = _get_coordinator(request)
    if getattr(request.app.state, "engine", None) is None:
        raise HTTPException(
            status_code=503,
            detail="No inference engine is loaded; the fleet cannot run missions.",
        )
    if req.max_subtasks:
        coordinator._max_subtasks = req.max_subtasks
    if req.max_parallel:
        coordinator._max_parallel = req.max_parallel
    mission = coordinator.submit(req.objective)
    return mission.to_dict()


@fleet_router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, request: Request):
    coordinator = _get_coordinator(request)
    mission = coordinator.store.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission.to_dict()


@fleet_router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str, request: Request):
    coordinator = _get_coordinator(request)
    if not coordinator.cancel(mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"status": "cancel_requested", "mission_id": mission_id}


__all__ = ["fleet_router"]
