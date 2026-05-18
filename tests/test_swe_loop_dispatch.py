"""Regression tests for Bug 4: SWE-bench dispatch through the agent loop
for all three cloud endpoints (Anthropic / OpenAI / Gemini).

Before the fix, ``baseline_cloud`` and ``skillorchestra`` gated the SWE
agent-loop call on ``cloud_endpoint == "anthropic"`` and silently fell
back to a one-shot ``_call_cloud`` for OpenAI / Gemini SWE tasks — a
"blind patch" that scored near zero. ``_loop_cloud`` in
``mini_swe_agent`` now dispatches per endpoint, so all three should
route through ``run_swe_agent_loop``.

These tests pin the dispatch behavior without doing any real cloud
calls: ``run_swe_agent_loop`` is patched in each agent module to record
the kwargs it was invoked with.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from openjarvis.agents._stubs import AgentContext
from openjarvis.agents.hybrid.baseline_cloud import BaselineCloudAgent
from openjarvis.agents.hybrid.skillorchestra import SkillOrchestraAgent


# ---------- helpers ----------

def _swe_task() -> Dict[str, Any]:
    """SWE-bench-shaped task that triggers the is_swe / swe_mode branch."""
    return {
        "task_id": "test__swe-1",
        "repo": "test/repo",
        "base_commit": "deadbeef",
        "problem_statement": "Fix the off-by-one in the parser.",
    }


def _gaia_task() -> Dict[str, Any]:
    """Non-SWE task (no repo / base_commit) — should hit the one-shot path."""
    return {"task_id": "gaia-1"}


def _loop_return(answer: str = "ok diff") -> Dict[str, Any]:
    """Shape that run_swe_agent_loop returns."""
    return {
        "answer": answer,
        "patch": "diff --git a/x b/x\n",
        "final_summary": "fixed",
        "tokens_in": 100,
        "tokens_out": 50,
        "tokens_local": 0,
        "tokens_cloud": 150,
        "cost_usd": 0.001,
        "turns": 3,
        "max_turns_hit": False,
        "workdir": "/tmp/x",
    }


def _make_baseline(cloud_endpoint: str) -> BaselineCloudAgent:
    return BaselineCloudAgent(
        engine=MagicMock(name="engine"),
        model="some-cloud-model",
        cloud_endpoint=cloud_endpoint,
        cfg={"cloud_max_tokens": 1024, "swe_max_turns": 5},
    )


def _make_skillorch(cloud_endpoint: str) -> SkillOrchestraAgent:
    # swe_use_agent_loop must be on for skillorchestra to enter the
    # swe_mode branch.
    return SkillOrchestraAgent(
        engine=MagicMock(name="engine"),
        model="some-cloud-model",
        cloud_endpoint=cloud_endpoint,
        cfg={
            "swe_use_agent_loop": True,
            "swe_max_turns": 5,
            "swe_turn_max_tokens": 1024,
        },
    )


def _ctx(task: Dict[str, Any]) -> AgentContext:
    ctx = AgentContext()
    ctx.metadata["task"] = task
    ctx.metadata["task_id"] = task.get("task_id", "")
    return ctx


# Router mock returns a JSON blob picking cloud-<cloud_model> so
# skillorchestra routes to the cloud worker (not local). The agent key now
# embeds the cell-configured cloud model — see skillorchestra._run_paradigm.
_ROUTER_JSON = (
    '{"chosen_agent": "cloud-some-cloud-model", '
    '"skill_weights": {"factual_recall": 0.0, "multi_step_reasoning": 0.0, '
    '"arithmetic": 0.0, "web_grounding": 0.0, "long_text_extraction": 0.0, '
    '"format_compliance": 0.0, "code_or_logic": 1.0}, '
    '"reasoning": "test"}'
)


# ---------- baseline_cloud ----------

@pytest.mark.parametrize("endpoint", ["anthropic", "openai", "gemini"])
def test_baseline_cloud_swe_uses_loop_for_all_endpoints(endpoint: str) -> None:
    """SWE task + any cloud endpoint → run_swe_agent_loop called with that
    endpoint. Pre-fix this only fired for anthropic; openai / gemini silently
    fell back to a one-shot ``_call_cloud`` blind-patch."""
    agent = _make_baseline(endpoint)
    task = _swe_task()
    ctx = _ctx(task)

    with patch(
        "openjarvis.agents.hybrid.baseline_cloud.run_swe_agent_loop",
        return_value=_loop_return(),
    ) as mock_loop, patch.object(
        BaselineCloudAgent, "_call_cloud"
    ) as mock_oneshot:
        answer, meta = agent._run_paradigm("Fix the bug.", ctx)

    assert mock_loop.call_count == 1, (
        f"SWE task with cloud_endpoint={endpoint!r} must dispatch to "
        f"run_swe_agent_loop, not the one-shot fallback"
    )
    assert mock_oneshot.call_count == 0, (
        f"_call_cloud one-shot should NOT be invoked on SWE for {endpoint!r}"
    )
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["cloud_endpoint"] == endpoint
    assert call_kwargs["backbone"] == "cloud"
    assert call_kwargs["backbone_model"] == "some-cloud-model"
    assert meta["tokens_cloud"] == 150


# Per the task spec — explicit per-endpoint variants for clarity in failure
# reports (parametrize above already covers them but these read as the
# named tests in the task description).

def test_baseline_cloud_anthropic_uses_loop() -> None:
    test_baseline_cloud_swe_uses_loop_for_all_endpoints("anthropic")


def test_baseline_cloud_openai_uses_loop() -> None:
    test_baseline_cloud_swe_uses_loop_for_all_endpoints("openai")


def test_baseline_cloud_gemini_uses_loop() -> None:
    test_baseline_cloud_swe_uses_loop_for_all_endpoints("gemini")


def test_baseline_cloud_gaia_uses_oneshot() -> None:
    """Non-SWE task → one-shot ``_call_cloud``, NOT the SWE agent loop.

    Regression guard against over-correcting Bug 4 by routing every task
    through the SWE loop (which would crash on GAIA without repo / commit).
    """
    agent = _make_baseline("openai")
    ctx = _ctx(_gaia_task())

    with patch(
        "openjarvis.agents.hybrid.baseline_cloud.run_swe_agent_loop",
    ) as mock_loop, patch.object(
        BaselineCloudAgent,
        "_call_cloud",
        return_value=("the answer", 10, 20),
    ) as mock_oneshot:
        answer, meta = agent._run_paradigm("What is 2+2?", ctx)

    assert mock_loop.call_count == 0, (
        "GAIA-shaped task must NOT enter the SWE agent loop"
    )
    assert mock_oneshot.call_count == 1
    assert answer == "the answer"
    assert meta["turns"] == 1
    assert meta["traces"]["mode"] == "one_shot"


# ---------- skillorchestra ----------

@pytest.mark.parametrize("endpoint", ["anthropic", "openai", "gemini"])
def test_skillorchestra_cloud_swe_uses_loop(endpoint: str) -> None:
    """For each cloud endpoint, when skillorchestra routes to the cloud
    worker on a SWE task it must call run_swe_agent_loop, not the one-shot
    ``_call_cloud`` fallback (the Bug-4 regression path)."""
    agent = _make_skillorch(endpoint)
    ctx = _ctx(_swe_task())

    # Router patches: anthropic path uses _call_anthropic with output_config;
    # openai / gemini routers use _call_openai / _call_gemini with prompt-only
    # JSON. Patch all three to be safe regardless of endpoint.
    with patch.object(
        SkillOrchestraAgent,
        "_call_anthropic",
        return_value=(_ROUTER_JSON, 5, 5, 0),
    ), patch.object(
        SkillOrchestraAgent,
        "_call_openai",
        return_value=(_ROUTER_JSON, 5, 5),
    ), patch.object(
        SkillOrchestraAgent,
        "_call_gemini",
        return_value=(_ROUTER_JSON, 5, 5),
    ), patch.object(
        SkillOrchestraAgent,
        "_call_cloud",
        return_value=("oneshot-answer", 99, 99),
    ) as mock_oneshot, patch(
        "openjarvis.agents.hybrid.skillorchestra.run_swe_agent_loop",
        return_value=_loop_return(),
    ) as mock_loop:
        answer, meta = agent._run_paradigm("Fix the bug.", ctx)

    assert mock_loop.call_count == 1, (
        f"skillorchestra cloud-worker SWE with endpoint={endpoint!r} must "
        f"dispatch through run_swe_agent_loop, not _call_cloud one-shot"
    )
    assert mock_oneshot.call_count == 0, (
        f"_call_cloud one-shot should NOT be invoked on SWE for {endpoint!r}"
    )
    call_kwargs = mock_loop.call_args.kwargs
    assert call_kwargs["cloud_endpoint"] == endpoint
    assert call_kwargs["backbone"] == "cloud"
    # chosen_agent must reflect the cell-configured cloud model (Bug A fix:
    # 2026-05-17), not a hardcoded "cloud-opus-4-7" string.
    assert meta["traces"]["chosen_agent"] == "cloud-some-cloud-model"


def test_skillorchestra_cloud_anthropic_uses_loop() -> None:
    test_skillorchestra_cloud_swe_uses_loop("anthropic")


def test_skillorchestra_cloud_openai_uses_loop() -> None:
    test_skillorchestra_cloud_swe_uses_loop("openai")


def test_skillorchestra_cloud_gemini_uses_loop() -> None:
    test_skillorchestra_cloud_swe_uses_loop("gemini")


# ---------- skillorchestra cloud-agent-key contract ----------
#
# Bug A (2026-05-17): the router used to advertise a hardcoded
# `cloud-opus-4-7` agent regardless of the cell-configured cloud model, so
# Haiku / Gemini cells saw Opus's competence + cost in the prompt. The fix
# plumbs `self._cloud_model` into the agent registry key. These assertions
# pin that contract.

def test_skillorchestra_cloud_key_matches_cloud_model() -> None:
    """Default competence / cost tables for a cell are keyed by the
    cell-configured cloud_model, not a hardcoded Opus string."""
    from openjarvis.agents.hybrid.skillorchestra import (
        _default_agent_competence,
        _default_agent_cost,
    )

    comp = _default_agent_competence("qwen-27b", "claude-haiku-4-5")
    cost = _default_agent_cost("qwen-27b", "claude-haiku-4-5")
    assert "cloud-claude-haiku-4-5" in comp
    assert "cloud-claude-haiku-4-5" in cost
    # And the hardcoded Opus key must NOT appear for a non-Opus cell.
    assert "cloud-claude-opus-4-7" not in comp
    assert "cloud-claude-opus-4-7" not in cost
    # Cost must come from the empirical per-task table — Haiku is ~$0.002,
    # NOT Opus's $0.014, so price ratio actually bites for the router.
    assert cost["cloud-claude-haiku-4-5"] < 0.005


def test_skillorchestra_chosen_agent_uses_cloud_model_name() -> None:
    """End-to-end: when a cell is configured with a non-Opus cloud, the
    trace's `chosen_agent` field must name that cloud (not 'cloud-opus-4-7')."""
    agent = SkillOrchestraAgent(
        engine=MagicMock(name="engine"),
        model="claude-haiku-4-5",
        cloud_endpoint="anthropic",
        cfg={"cloud_max_tokens": 256},
    )
    # Router emits the right haiku key; weight loads onto code_or_logic.
    router_json = (
        '{"chosen_agent": "cloud-claude-haiku-4-5", '
        '"skill_weights": {"factual_recall": 0.0, "multi_step_reasoning": 0.0, '
        '"arithmetic": 0.0, "web_grounding": 0.0, "long_text_extraction": 0.0, '
        '"format_compliance": 0.0, "code_or_logic": 1.0}, '
        '"reasoning": "test"}'
    )
    ctx = _ctx({"task_id": "gaia-1"})
    with patch.object(
        SkillOrchestraAgent, "_call_anthropic",
        return_value=(router_json, 5, 5, 0),
    ), patch.object(
        SkillOrchestraAgent, "_call_cloud",
        return_value=("the answer", 10, 20),
    ):
        _, meta = agent._run_paradigm("hello", ctx)

    assert meta["traces"]["chosen_agent"] == "cloud-claude-haiku-4-5"
    assert meta["traces"]["worker_model"] == "claude-haiku-4-5"
