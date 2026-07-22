"""Instantly.ai campaign tool — set up and manage cold e-mail campaigns.

Wraps the Instantly API v2 (https://developer.instantly.ai). Authentication
uses a Bearer API key read from the ``INSTANTLY_API_KEY`` environment
variable (create one under Instantly → Settings → Integrations → API Keys).

Campaigns are created **paused**; sending only starts after an explicit
``activate_campaign`` action, so the agent can build and review a campaign
without accidentally e-mailing anyone.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_API_BASE = "https://api.instantly.ai/api/v2"
_TIMEOUT = 30.0

_ACTIONS = frozenset(
    {
        "create_campaign",
        "add_leads",
        "list_campaigns",
        "get_campaign",
        "activate_campaign",
        "pause_campaign",
        "get_analytics",
        "list_accounts",
    }
)

# Instantly expects days keyed "0" (Sunday) … "6" (Saturday).
_WEEKDAYS = {"1": True, "2": True, "3": True, "4": True, "5": True}


def _api_key() -> Optional[str]:
    return os.environ.get("INSTANTLY_API_KEY") or None


def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Perform an authenticated request against the Instantly v2 API."""
    resp = httpx.request(
        method,
        f"{_API_BASE}{path}",
        headers={"Authorization": f"Bearer {_api_key()}"},
        json=json_body,
        params=params,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    if not resp.content:
        return {}
    return resp.json()


def _build_sequence(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert simple step dicts into the Instantly sequence structure.

    Input steps look like ``{"subject": str, "body": str, "delay": int}``;
    ``delay`` is days to wait after the previous step (ignored on step 1).
    A step without a subject continues the previous thread (empty subject).
    """
    api_steps = []
    for i, step in enumerate(steps):
        api_steps.append(
            {
                "type": "email",
                "delay": int(step.get("delay", 2)) if i > 0 else 0,
                "variants": [
                    {
                        "subject": step.get("subject", ""),
                        "body": step.get("body", ""),
                    }
                ],
            }
        )
    return [{"steps": api_steps}]


def _build_schedule(
    *,
    timezone: str,
    from_time: str,
    to_time: str,
    days: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    return {
        "schedules": [
            {
                "name": "Default schedule",
                "timing": {"from": from_time, "to": to_time},
                "days": days or dict(_WEEKDAYS),
                "timezone": timezone,
            }
        ]
    }


@ToolRegistry.register("instantly_campaign")
class InstantlyCampaignTool(BaseTool):
    """Create and manage Instantly.ai cold e-mail campaigns."""

    tool_id = "instantly_campaign"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="instantly_campaign",
            description=(
                "Manage Instantly.ai e-mail campaigns: create a campaign"
                " with a follow-up sequence and sending schedule, add"
                " leads, list/inspect campaigns, activate or pause"
                " sending, and fetch analytics. Campaigns are created"
                " paused — nothing is sent until 'activate_campaign' is"
                " called explicitly. Requires the INSTANTLY_API_KEY"
                " environment variable."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": sorted(_ACTIONS),
                        "description": (
                            "Operation to perform. 'create_campaign' needs"
                            " name + steps; 'add_leads' needs campaign_id +"
                            " leads; 'activate_campaign', 'pause_campaign',"
                            " 'get_campaign' and 'get_analytics' need"
                            " campaign_id; 'list_campaigns' and"
                            " 'list_accounts' need nothing else."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Campaign name (create_campaign).",
                    },
                    "steps": {
                        "type": "array",
                        "description": (
                            "E-mail sequence for create_campaign. Each item:"
                            " {subject, body, delay}. 'delay' = days after"
                            " the previous e-mail (default 2). Leave"
                            " 'subject' empty on follow-ups to send them in"
                            " the same thread. Use {{firstName}},"
                            " {{companyName}} and {{personalization}}"
                            " placeholders for personalization."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                                "delay": {"type": "integer"},
                            },
                            "required": ["body"],
                        },
                    },
                    "email_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Sending account e-mail addresses to attach to"
                            " the campaign (must already exist in the"
                            " Instantly workspace; see 'list_accounts')."
                        ),
                    },
                    "daily_limit": {
                        "type": "integer",
                        "description": (
                            "Max e-mails per day per sending account"
                            " (default 30 — safe warm-up volume)."
                        ),
                    },
                    "timezone": {
                        "type": "string",
                        "description": (
                            "IANA timezone for the sending window"
                            " (default 'Europe/Istanbul')."
                        ),
                    },
                    "from_time": {
                        "type": "string",
                        "description": "Sending window start, HH:MM (default 09:00).",
                    },
                    "to_time": {
                        "type": "string",
                        "description": "Sending window end, HH:MM (default 17:00).",
                    },
                    "campaign_id": {
                        "type": "string",
                        "description": "Campaign ID for campaign-scoped actions.",
                    },
                    "leads": {
                        "type": "array",
                        "description": (
                            "Leads for add_leads. Each item: {email,"
                            " first_name, last_name, company_name,"
                            " personalization, custom_variables}."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "email": {"type": "string"},
                                "first_name": {"type": "string"},
                                "last_name": {"type": "string"},
                                "company_name": {"type": "string"},
                                "personalization": {"type": "string"},
                                "custom_variables": {"type": "object"},
                            },
                            "required": ["email"],
                        },
                    },
                },
                "required": ["action"],
            },
            category="marketing",
            required_capabilities=["network:fetch"],
            timeout_seconds=60.0,
        )

    # -- action handlers ---------------------------------------------------

    def _create_campaign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        steps = params.get("steps") or []
        if not name:
            raise ValueError("'name' is required for create_campaign.")
        if not steps:
            raise ValueError(
                "'steps' is required for create_campaign —"
                " provide at least one e-mail (subject + body)."
            )
        body: Dict[str, Any] = {
            "name": name,
            "campaign_schedule": _build_schedule(
                timezone=params.get("timezone", "Europe/Istanbul"),
                from_time=params.get("from_time", "09:00"),
                to_time=params.get("to_time", "17:00"),
            ),
            "sequences": _build_sequence(steps),
            "daily_limit": int(params.get("daily_limit", 30)),
            "stop_on_reply": True,
            "link_tracking": False,
            "open_tracking": False,
            "text_only": True,
        }
        if params.get("email_list"):
            body["email_list"] = list(params["email_list"])
        return _request("POST", "/campaigns", json_body=body)

    def _add_leads(self, params: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id = params.get("campaign_id")
        leads = params.get("leads") or []
        if not campaign_id:
            raise ValueError("'campaign_id' is required for add_leads.")
        if not leads:
            raise ValueError("'leads' is required for add_leads.")
        created, errors = [], []
        for lead in leads:
            payload = {"campaign": campaign_id}
            for src, dst in (
                ("email", "email"),
                ("first_name", "first_name"),
                ("last_name", "last_name"),
                ("company_name", "company_name"),
                ("personalization", "personalization"),
                ("custom_variables", "custom_variables"),
            ):
                if lead.get(src) is not None:
                    payload[dst] = lead[src]
            try:
                created.append(_request("POST", "/leads", json_body=payload))
            except httpx.HTTPStatusError as exc:
                errors.append(
                    {
                        "email": lead.get("email"),
                        "status": exc.response.status_code,
                        "detail": exc.response.text[:500],
                    }
                )
        return {
            "added": len(created),
            "failed": len(errors),
            "errors": errors,
        }

    def _dispatch(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "create_campaign":
            return self._create_campaign(params)
        if action == "add_leads":
            return self._add_leads(params)
        if action == "list_campaigns":
            return _request("GET", "/campaigns", params={"limit": 50})
        if action == "list_accounts":
            return _request("GET", "/accounts", params={"limit": 50})

        campaign_id = params.get("campaign_id")
        if not campaign_id:
            raise ValueError(f"'campaign_id' is required for {action}.")
        if action == "get_campaign":
            return _request("GET", f"/campaigns/{campaign_id}")
        if action == "activate_campaign":
            return _request("POST", f"/campaigns/{campaign_id}/activate")
        if action == "pause_campaign":
            return _request("POST", f"/campaigns/{campaign_id}/pause")
        if action == "get_analytics":
            return _request("GET", "/campaigns/analytics", params={"id": campaign_id})
        raise ValueError(f"Unknown action: {action}")

    def execute(self, **params: Any) -> ToolResult:
        action = params.get("action", "")
        if action not in _ACTIONS:
            return ToolResult(
                tool_name="instantly_campaign",
                content=(
                    f"Unknown action: {action!r}."
                    f" Allowed: {', '.join(sorted(_ACTIONS))}."
                ),
                success=False,
            )

        if not _api_key():
            return ToolResult(
                tool_name="instantly_campaign",
                content=(
                    "INSTANTLY_API_KEY is not set. Create an API key in"
                    " Instantly (Settings → Integrations → API Keys) and"
                    " export it as INSTANTLY_API_KEY."
                ),
                success=False,
            )

        try:
            data = self._dispatch(action, params)
        except ValueError as exc:
            return ToolResult(
                tool_name="instantly_campaign",
                content=str(exc),
                success=False,
            )
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                tool_name="instantly_campaign",
                content=(
                    f"Instantly API error {exc.response.status_code}"
                    f" on {action}: {exc.response.text[:1000]}"
                ),
                success=False,
                metadata={"status_code": exc.response.status_code},
            )
        except httpx.RequestError as exc:
            return ToolResult(
                tool_name="instantly_campaign",
                content=f"Request error on {action}: {exc}",
                success=False,
            )

        return ToolResult(
            tool_name="instantly_campaign",
            content=json.dumps(data, ensure_ascii=False, indent=2),
            success=True,
            metadata={"action": action},
        )


__all__ = ["InstantlyCampaignTool"]
