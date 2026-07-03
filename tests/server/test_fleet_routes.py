"""Tests for the /v1/fleet API routes."""

from __future__ import annotations

import json
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.core.events import EventBus  # noqa: E402
from openjarvis.server.fleet_routes import fleet_router  # noqa: E402


class PlanningFakeEngine:
    def generate(self, messages: list, *, model: str = "", **kw):
        text = " ".join(str(getattr(m, "content", "")) for m in messages or [])
        if "mission planner for a fleet" in text:
            content = json.dumps(
                [{"title": "T", "description": "explain things", "role": "tutor"}]
            )
        else:
            content = "answer"
        return {"content": content, "usage": {"total_tokens": 3}}


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(fleet_router)
    app.state.engine = PlanningFakeEngine()
    app.state.model = "fake-model"
    app.state.bus = EventBus()
    return TestClient(app)


def _wait_for_mission(
    client: TestClient, mission_id: str, timeout: float = 10.0
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/v1/fleet/missions/{mission_id}").json()
        if data["status"] in ("completed", "failed", "canceled"):
            return data
        time.sleep(0.05)
    raise AssertionError("mission did not finish in time")


class TestFleetRoutes:
    def test_status(self, client):
        data = client.get("/v1/fleet/status").json()
        assert data["roles"] >= 90
        assert "engineering" in data["categories"]
        assert data["missions_active"] == 0

    def test_list_roles_with_filters(self, client):
        all_roles = client.get("/v1/fleet/roles").json()["roles"]
        assert len(all_roles) >= 90
        eng = client.get("/v1/fleet/roles", params={"category": "engineering"}).json()[
            "roles"
        ]
        assert eng and all(r["category"] == "engineering" for r in eng)
        travel = client.get("/v1/fleet/roles", params={"q": "travel"}).json()["roles"]
        assert any(r["role_id"] == "travel_planner" for r in travel)

    def test_match_preview(self, client):
        data = client.get(
            "/v1/fleet/roles/match", params={"task": "write a blog post", "top_k": 3}
        ).json()
        assert data["matches"]
        assert data["matches"][0]["role"]["role_id"] == "blog_writer"

    def test_mission_lifecycle(self, client):
        created = client.post("/v1/fleet/missions", json={"objective": "explain AI"})
        assert created.status_code == 200
        mission_id = created.json()["mission_id"]

        final = _wait_for_mission(client, mission_id)
        assert final["status"] == "completed"
        assert final["subtasks"][0]["role_id"] == "tutor"
        assert final["final_output"] == "answer"

        listed = client.get("/v1/fleet/missions").json()["missions"]
        assert any(m["mission_id"] == mission_id for m in listed)
        # Summary listing omits subtask bodies
        assert "subtasks" not in listed[0]

    def test_mission_requires_engine(self):
        app = FastAPI()
        app.include_router(fleet_router)
        app.state.engine = None
        app.state.model = ""
        app.state.bus = EventBus()
        client = TestClient(app)
        res = client.post("/v1/fleet/missions", json={"objective": "x"})
        assert res.status_code == 503

    def test_missing_mission_404(self, client):
        assert client.get("/v1/fleet/missions/nope").status_code == 404
        assert client.post("/v1/fleet/missions/nope/cancel").status_code == 404

    def test_empty_objective_rejected(self, client):
        res = client.post("/v1/fleet/missions", json={"objective": ""})
        assert res.status_code == 422
