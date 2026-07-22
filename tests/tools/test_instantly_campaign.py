"""Tests for the Instantly.ai campaign tool."""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from openjarvis.tools.instantly_campaign import (
    InstantlyCampaignTool,
    _build_sequence,
)

_API = "https://api.instantly.ai/api/v2"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("INSTANTLY_API_KEY", "test-key")


class TestSpec:
    def test_spec_name_and_category(self):
        tool = InstantlyCampaignTool()
        assert tool.spec.name == "instantly_campaign"
        assert tool.spec.category == "marketing"

    def test_spec_required_capabilities(self):
        tool = InstantlyCampaignTool()
        assert "network:fetch" in tool.spec.required_capabilities

    def test_spec_requires_action(self):
        tool = InstantlyCampaignTool()
        assert "action" in tool.spec.parameters["required"]

    def test_is_external(self):
        assert InstantlyCampaignTool.is_local is False


class TestValidation:
    def test_unknown_action(self):
        result = InstantlyCampaignTool().execute(action="delete_everything")
        assert result.success is False
        assert "Unknown action" in result.content

    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("INSTANTLY_API_KEY", raising=False)
        result = InstantlyCampaignTool().execute(action="list_campaigns")
        assert result.success is False
        assert "INSTANTLY_API_KEY" in result.content

    def test_create_campaign_requires_name(self):
        result = InstantlyCampaignTool().execute(
            action="create_campaign", steps=[{"body": "hi"}]
        )
        assert result.success is False
        assert "'name'" in result.content

    def test_create_campaign_requires_steps(self):
        result = InstantlyCampaignTool().execute(action="create_campaign", name="Test")
        assert result.success is False
        assert "'steps'" in result.content

    def test_activate_requires_campaign_id(self):
        result = InstantlyCampaignTool().execute(action="activate_campaign")
        assert result.success is False
        assert "'campaign_id'" in result.content


class TestSequenceBuilder:
    def test_first_step_has_no_delay(self):
        seq = _build_sequence(
            [
                {"subject": "hello", "body": "a", "delay": 5},
                {"body": "b", "delay": 3},
            ]
        )
        steps = seq[0]["steps"]
        assert steps[0]["delay"] == 0
        assert steps[1]["delay"] == 3

    def test_followup_defaults_to_two_days_same_thread(self):
        seq = _build_sequence([{"subject": "s", "body": "a"}, {"body": "b"}])
        steps = seq[0]["steps"]
        assert steps[1]["delay"] == 2
        assert steps[1]["variants"][0]["subject"] == ""


class TestApiCalls:
    @respx.mock
    def test_create_campaign_payload(self):
        route = respx.post(f"{_API}/campaigns").mock(
            return_value=Response(200, json={"id": "camp-1", "name": "Demo"})
        )
        result = InstantlyCampaignTool().execute(
            action="create_campaign",
            name="Demo",
            steps=[{"subject": "hey", "body": "merhaba"}],
            email_list=["sender@acme.com"],
            daily_limit=25,
        )
        assert result.success is True
        payload = json.loads(route.calls[0].request.content)
        assert payload["name"] == "Demo"
        assert payload["daily_limit"] == 25
        assert payload["email_list"] == ["sender@acme.com"]
        assert payload["stop_on_reply"] is True
        schedule = payload["campaign_schedule"]["schedules"][0]
        assert schedule["timezone"] == "Europe/Istanbul"
        assert schedule["timing"] == {"from": "09:00", "to": "17:00"}
        auth = route.calls[0].request.headers["authorization"]
        assert auth == "Bearer test-key"

    @respx.mock
    def test_add_leads_reports_partial_failure(self):
        respx.post(f"{_API}/leads").mock(
            side_effect=[
                Response(200, json={"id": "lead-1"}),
                Response(400, json={"error": "invalid email"}),
            ]
        )
        result = InstantlyCampaignTool().execute(
            action="add_leads",
            campaign_id="camp-1",
            leads=[
                {"email": "a@x.com", "first_name": "Ada"},
                {"email": "bad"},
            ],
        )
        assert result.success is True
        data = json.loads(result.content)
        assert data["added"] == 1
        assert data["failed"] == 1
        assert data["errors"][0]["email"] == "bad"

    @respx.mock
    def test_activate_campaign(self):
        respx.post(f"{_API}/campaigns/camp-1/activate").mock(
            return_value=Response(200, json={"status": "active"})
        )
        result = InstantlyCampaignTool().execute(
            action="activate_campaign", campaign_id="camp-1"
        )
        assert result.success is True
        assert "active" in result.content

    @respx.mock
    def test_api_error_is_surfaced(self):
        respx.get(f"{_API}/campaigns").mock(
            return_value=Response(401, json={"error": "bad key"})
        )
        result = InstantlyCampaignTool().execute(action="list_campaigns")
        assert result.success is False
        assert "401" in result.content
