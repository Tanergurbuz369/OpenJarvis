"""Tests for the GAIA web_search wiring (2026-05-17).

Confirms that when a GAIA cell sets ``method_cfg.web_search.enabled = true``
and the cloud endpoint is Anthropic, every paradigm declares the native
``web_search_20250305`` server-side tool on its Anthropic call. Uses mocks
— no real API calls.

Also confirms the default (``web_search`` absent / disabled) stays
one-shot and does NOT declare the tool, preserving back-compat with the
currently running n=100 cells.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.hybrid._base import (
    LocalCloudAgent,
    build_web_search_tool,
    web_search_cfg,
)


# ---------------------------------------------------------------------------
# 1. Schema parser
# ---------------------------------------------------------------------------

def test_web_search_cfg_default_off() -> None:
    assert web_search_cfg(None) == (False, 8)
    assert web_search_cfg({}) == (False, 8)
    assert web_search_cfg({"web_search": None}) == (False, 8)


def test_web_search_cfg_enabled() -> None:
    assert web_search_cfg({"web_search": {"enabled": True}}) == (True, 8)
    assert web_search_cfg({"web_search": {"enabled": True, "max_uses": 3}}) == (True, 3)
    assert web_search_cfg({"web_search": {"enabled": False, "max_uses": 5}}) == (False, 5)


def test_build_web_search_tool_shape() -> None:
    tool = build_web_search_tool(5)
    assert tool == {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
    }


# ---------------------------------------------------------------------------
# 2. Baseline cloud GAIA cell declares the tool when opted in
# ---------------------------------------------------------------------------

def _fake_anthropic_response(
    text: str = "FINAL ANSWER: 42",
    n_searches: int = 2,
    input_tokens: int = 100,
    output_tokens: int = 50,
):
    """Build a minimal Anthropic-shaped response object."""
    return SimpleNamespace(
        content=[SimpleNamespace(
            type="text", text=text,
            # the serializer probes a fixed attr list; only `text` is
            # needed for the text block path.
        )],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            server_tool_use=SimpleNamespace(web_search_requests=n_searches),
        ),
        stop_reason="end_turn",
    )


class _FakeMessages:
    """Captures the create() kwargs so the test can assert what was sent."""

    def __init__(self):
        self.last_kwargs = None
        self.responses = [_fake_anthropic_response()]
        self.calls = 0

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


class _FakeAnthropic:
    """anthropic.Anthropic() stub. Stores messages on a class attr so the
    test can pull it out after the agent's call."""

    last_messages = None

    def __init__(self, *args, **kwargs):
        self.messages = _FakeMessages()
        type(self).last_messages = self.messages


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Patch anthropic.Anthropic at the SDK level so every paradigm's
    raw client construction picks up the fake. Importing the real
    library is fine — the agent uses ``anthropic.Anthropic()`` only.
    """
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    yield _FakeAnthropic


def test_baseline_cloud_declares_web_search_on_gaia_when_enabled(fake_anthropic):
    from openjarvis.agents.hybrid.baseline_cloud import BaselineCloudAgent

    agent = BaselineCloudAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        cfg={
            "cloud_max_tokens": 1024,
            "web_search": {"enabled": True, "max_uses": 4},
            "gaia_max_turns": 2,
        },
    )
    ctx = AgentContext(metadata={
        "task": {"task_id": "t1", "question": "What is X?"},
        "task_id": "t1",
    })
    result = agent.run("What is X?", ctx)

    sent = fake_anthropic.last_messages.last_kwargs
    assert sent is not None, "Anthropic client was never called"
    assert "tools" in sent, "web_search tool was not declared"
    assert sent["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 4}
    ]
    # Per-row web_search_uses surfaced through meta.
    assert result.metadata["web_search_uses"] == 2


def test_baseline_cloud_does_not_declare_tool_when_disabled(fake_anthropic):
    from openjarvis.agents.hybrid.baseline_cloud import BaselineCloudAgent

    agent = BaselineCloudAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        cfg={"cloud_max_tokens": 1024},  # no web_search block — default OFF
    )
    ctx = AgentContext(metadata={
        "task": {"task_id": "t2", "question": "What is X?"},
        "task_id": "t2",
    })
    agent.run("What is X?", ctx)

    sent = fake_anthropic.last_messages.last_kwargs
    assert sent is not None
    assert "tools" not in sent, (
        "Default behavior MUST be one-shot with no tools declared — "
        "tools must only appear when method_cfg.web_search.enabled = true."
    )


def test_baseline_cloud_web_search_skipped_on_non_anthropic(monkeypatch):
    """Non-Anthropic endpoint with web_search.enabled=true must not crash
    and must not invoke a fake local web_search — it falls back to the
    one-shot path (logged as web_search_skipped)."""
    from openjarvis.agents.hybrid import baseline_cloud as bc_mod
    from openjarvis.agents.hybrid.baseline_cloud import BaselineCloudAgent

    # Stub the cloud call so we don't hit OpenAI.
    def fake_call_cloud(self, *, user, system=None, max_tokens=4096,
                       temperature=0.0, **kwargs):
        return "FINAL ANSWER: x", 10, 5

    monkeypatch.setattr(
        bc_mod.BaselineCloudAgent, "_call_cloud", fake_call_cloud, raising=True,
    )

    agent = BaselineCloudAgent(
        engine=None,
        model="gpt-5",
        cloud_endpoint="openai",
        cfg={"cloud_max_tokens": 1024, "web_search": {"enabled": True}},
    )
    ctx = AgentContext(metadata={
        "task": {"task_id": "t3", "question": "X?"},
        "task_id": "t3",
    })
    res = agent.run("X?", ctx)
    # Falls through to one-shot path; no crash, no fake web_search.
    assert res.metadata["web_search_uses"] == 0
