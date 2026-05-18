"""Per-row ``tool_calls`` tracking across hybrid paradigms (2026-05-18).

Confirms each paradigm surfaces a top-level ``tool_calls: int`` in the
``AgentResult.metadata`` so the runner can write it into ``results.jsonl``.
Definition per paradigm:

  - SWE-bench cells: bash turns from ``run_swe_agent_loop``. One tool call
    per bash command the agent ran.
  - GAIA cells: number of native ``web_search`` invocations the cloud
    backbone made. Zero for one-shot GAIA paths and zero for paradigms
    whose GAIA path is just text-passing (e.g. Minions w/o prefetch).

The legacy ``skillorchestra`` tool_calls numbers in
``docs/results-table.md`` came from a defunct telemetry path; this
re-establishes the contract on the actual row-write path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from openjarvis.agents._stubs import AgentContext


# ---------------------------------------------------------------------------
# Anthropic stub (web_search agent loop emits N web_search_requests).
# ---------------------------------------------------------------------------

def _fake_anthropic_response(text: str = "FINAL ANSWER: 7", n_searches: int = 3):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            server_tool_use=SimpleNamespace(web_search_requests=n_searches),
        ),
        stop_reason="end_turn",
    )


class _FakeMessages:
    def __init__(self, n_searches: int = 3):
        self.n_searches = n_searches
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        # Each anthropic call returns the same shape; total searches
        # accumulate via repeated calls (advisors does 2 executor passes,
        # each reporting its own n_searches).
        return _fake_anthropic_response(n_searches=self.n_searches)


class _FakeAnthropic:
    last_messages = None

    def __init__(self, *args, **kwargs):
        self.messages = _FakeMessages(n_searches=3)
        type(self).last_messages = self.messages


@pytest.fixture
def fake_anthropic(monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    yield _FakeAnthropic


# ---------------------------------------------------------------------------
# 1. baseline_cloud GAIA — tool_calls == n_searches on the agent-loop path.
# ---------------------------------------------------------------------------

def test_baseline_cloud_gaia_tool_calls_eq_web_searches(fake_anthropic):
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
    ctx = AgentContext(metadata={"task": {"task_id": "t1", "question": "X?"}, "task_id": "t1"})
    result = agent.run("X?", ctx)
    tc = result.metadata.get("tool_calls")
    assert isinstance(tc, int)
    assert tc == result.metadata["web_search_uses"] == 3


def test_baseline_cloud_gaia_oneshot_tool_calls_zero(monkeypatch):
    """The one-shot GAIA path makes zero countable tool calls."""
    from openjarvis.agents.hybrid import baseline_cloud as bc_mod
    from openjarvis.agents.hybrid.baseline_cloud import BaselineCloudAgent

    def fake_call_cloud(self, *, user, system=None, max_tokens=4096,
                       temperature=0.0, **kwargs):
        return "FINAL ANSWER: x", 10, 5

    monkeypatch.setattr(bc_mod.BaselineCloudAgent, "_call_cloud", fake_call_cloud)
    agent = BaselineCloudAgent(
        engine=None,
        model="gpt-5",
        cloud_endpoint="openai",
        cfg={"cloud_max_tokens": 1024},
    )
    ctx = AgentContext(metadata={"task": {"task_id": "t2", "question": "X?"}, "task_id": "t2"})
    result = agent.run("X?", ctx)
    assert isinstance(result.metadata.get("tool_calls"), int)
    assert result.metadata["tool_calls"] == 0


# ---------------------------------------------------------------------------
# 2. advisors GAIA — tool_calls == n_searches summed across executor passes.
# ---------------------------------------------------------------------------

def test_advisors_gaia_tool_calls_sums_search_counts(fake_anthropic, monkeypatch):
    from openjarvis.agents.hybrid.advisors import AdvisorsAgent

    # Stub the local vLLM advisor call so we don't need a server.
    def fake_vllm(model, endpoint, *, user, max_tokens, temperature,
                  enable_thinking=False):
        return "be more careful", 50, 10

    monkeypatch.setattr(
        "openjarvis.agents.hybrid.advisors.AdvisorsAgent._call_vllm",
        staticmethod(fake_vllm),
    )

    agent = AdvisorsAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        local_model="qwen",
        local_endpoint="http://x",
        cfg={
            "executor_max_tokens": 1024,
            "advisor_max_tokens": 512,
            "web_search": {"enabled": True, "max_uses": 4},
            "gaia_max_turns": 2,
        },
    )
    ctx = AgentContext(metadata={"task": {"task_id": "t3", "question": "X?"}, "task_id": "t3"})
    result = agent.run("X?", ctx)
    tc = result.metadata.get("tool_calls")
    assert isinstance(tc, int)
    # Two executor passes, each reports 3 searches → 6 total.
    assert tc == result.metadata["web_search_uses"] == 6


# ---------------------------------------------------------------------------
# 3. minions GAIA — tool_calls == prefetch n_searches.
# ---------------------------------------------------------------------------

def test_minions_gaia_tool_calls_eq_prefetch_searches(monkeypatch):
    from openjarvis.agents.hybrid import minions as minions_mod
    from openjarvis.agents.hybrid.minions import MinionsAgent

    # Skip the Minions import / patch dance entirely by stubbing _run_paradigm's
    # protocol layer. Easiest: stub _prefetch_context + replace Minions class.
    def fake_prefetch(question, endpoint, model, max_uses):
        return {
            "text": "stub digest",
            "tokens": 100,
            "cost_usd": 0.01,
            "n_searches": 2,
        }

    class _FakeProtocol:
        def __init__(self, **kw):
            pass

        def __call__(self, *args, **kw):
            return {
                "final_answer": "FINAL ANSWER: 42",
                "supervisor_messages": [],
                "worker_messages": [],
                "timing": {},
                "log_file": "/dev/null",
                "local_usage": SimpleNamespace(prompt_tokens=10, completion_tokens=5),
                "remote_usage": SimpleNamespace(prompt_tokens=20, completion_tokens=10),
            }

    fake_minions_module = SimpleNamespace(
        clients=SimpleNamespace(
            anthropic=SimpleNamespace(AnthropicClient=lambda **kw: None),
            openai=SimpleNamespace(OpenAIClient=lambda **kw: None),
        ),
        minion=SimpleNamespace(Minion=_FakeProtocol),
        minions=SimpleNamespace(Minions=_FakeProtocol),
    )

    import sys
    monkeypatch.setitem(sys.modules, "minions", fake_minions_module)
    monkeypatch.setitem(sys.modules, "minions.clients", fake_minions_module.clients)
    monkeypatch.setitem(sys.modules, "minions.clients.anthropic", fake_minions_module.clients.anthropic)
    monkeypatch.setitem(sys.modules, "minions.clients.openai", fake_minions_module.clients.openai)
    monkeypatch.setitem(sys.modules, "minions.minion", fake_minions_module.minion)
    monkeypatch.setitem(sys.modules, "minions.minions", fake_minions_module.minions)
    monkeypatch.setattr(minions_mod, "_apply_patches_once", lambda: None)
    monkeypatch.setattr(minions_mod, "_prefetch_context", fake_prefetch)

    agent = MinionsAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        local_model="qwen",
        local_endpoint="http://x",
        cfg={
            "mode": "minion",
            "max_rounds": 2,
            "web_search": {"enabled": True, "max_uses": 4},
        },
    )
    ctx = AgentContext(metadata={
        "task": {"task_id": "tm", "question": "What is X?"},
        "task_id": "tm",
    })
    result = agent.run("What is X?", ctx)
    tc = result.metadata.get("tool_calls")
    assert isinstance(tc, int)
    assert tc == 2  # matches the stubbed prefetch n_searches


# ---------------------------------------------------------------------------
# 4. SWE path — tool_calls equals bash turns from run_swe_agent_loop.
#    We stub run_swe_agent_loop directly so we don't need a repo / vLLM /
#    Anthropic.
# ---------------------------------------------------------------------------

def _stub_swe_loop(turns: int = 7):
    """Return a stub matching ``run_swe_agent_loop``'s output shape."""
    def _stub(task, **kwargs):
        return {
            "answer": "stub\n\n```diff\n--- a\n+++ b\n```",
            "patch": "--- a\n+++ b\n",
            "final_summary": "stub",
            "tokens_in": 200,
            "tokens_out": 100,
            "tokens_local": 0,
            "tokens_cloud": 300,
            "cost_usd": 0.05,
            "turns": turns,
            "max_turns_hit": False,
            "workdir": "/tmp/stub",
        }
    return _stub


def test_baseline_cloud_swe_tool_calls_eq_bash_turns(monkeypatch):
    from openjarvis.agents.hybrid import baseline_cloud as bc_mod
    from openjarvis.agents.hybrid.baseline_cloud import BaselineCloudAgent

    monkeypatch.setattr(bc_mod, "run_swe_agent_loop", _stub_swe_loop(turns=11))

    agent = BaselineCloudAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        cfg={"swe_max_turns": 30, "cloud_max_tokens": 4096},
    )
    task = {
        "task_id": "swe1",
        "problem_statement": "fix it",
        "repo": "a/b",
        "base_commit": "deadbeef",
    }
    ctx = AgentContext(metadata={"task": task, "task_id": "swe1"})
    result = agent.run("fix it", ctx)
    tc = result.metadata.get("tool_calls")
    assert isinstance(tc, int)
    assert tc == 11


def test_minions_swe_tool_calls_eq_worker_bash_turns(monkeypatch):
    from openjarvis.agents.hybrid import minions as minions_mod
    from openjarvis.agents.hybrid.minions import MinionsAgent

    monkeypatch.setattr(minions_mod, "run_swe_agent_loop", _stub_swe_loop(turns=9))

    def fake_call_cloud(self, *, user, system=None, max_tokens=4096,
                       temperature=0.0, **kwargs):
        return "plan: do X", 50, 25

    monkeypatch.setattr(minions_mod.MinionsAgent, "_call_cloud", fake_call_cloud)

    agent = MinionsAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        local_model="qwen",
        local_endpoint="http://x",
        cfg={"swe_use_agent_loop": True, "supervisor_max_tokens": 512},
    )
    task = {
        "task_id": "swe2",
        "problem_statement": "fix it",
        "repo": "a/b",
        "base_commit": "deadbeef",
    }
    ctx = AgentContext(metadata={"task": task, "task_id": "swe2"})
    result = agent.run("fix it", ctx)
    tc = result.metadata.get("tool_calls")
    assert isinstance(tc, int)
    assert tc == 9  # only the worker subloop counts; supervisor is text


def test_advisors_swe_tool_calls_sums_both_executor_passes(monkeypatch):
    from openjarvis.agents.hybrid import advisors as adv_mod
    from openjarvis.agents.hybrid.advisors import AdvisorsAgent

    # Both calls to run_swe_agent_loop return turns=4; sum should be 8.
    monkeypatch.setattr(adv_mod, "run_swe_agent_loop", _stub_swe_loop(turns=4))

    def fake_vllm(model, endpoint, *, user, max_tokens, temperature,
                  enable_thinking=False):
        return "advise", 30, 10

    monkeypatch.setattr(
        adv_mod.AdvisorsAgent, "_call_vllm", staticmethod(fake_vllm),
    )

    agent = AdvisorsAgent(
        engine=None,
        model="claude-opus-4-7",
        cloud_endpoint="anthropic",
        local_model="qwen",
        local_endpoint="http://x",
        cfg={"swe_use_agent_loop": True},
    )
    task = {
        "task_id": "swe3",
        "problem_statement": "fix it",
        "repo": "a/b",
        "base_commit": "deadbeef",
    }
    ctx = AgentContext(metadata={"task": task, "task_id": "swe3"})
    result = agent.run("fix it", ctx)
    tc = result.metadata.get("tool_calls")
    assert isinstance(tc, int)
    assert tc == 8  # initial + final executor passes, each 4 bash turns


# ---------------------------------------------------------------------------
# 5. Runner row contract — _run_one writes tool_calls into the row.
# ---------------------------------------------------------------------------

def test_runner_row_includes_tool_calls(monkeypatch):
    """The runner's ``_run_one`` must surface ``tool_calls`` from meta
    into the top-level row that ends up in ``results.jsonl``."""
    from openjarvis.agents._stubs import AgentResult
    from openjarvis.agents.hybrid import runner

    class _StubAgent:
        def run(self, prompt, ctx):
            return AgentResult(
                content="FINAL ANSWER: x",
                metadata={
                    "tokens_local": 0,
                    "tokens_cloud": 100,
                    "cost_usd": 0.01,
                    "latency_s": 0.1,
                    "web_search_uses": 2,
                    "tool_calls": 5,
                    "traces": {},
                },
                turns=1,
            )

    task = {"task_id": "row1", "question": "x", "reference": "x", "metadata": {}}
    row = runner._run_one(_StubAgent(), "gaia", task, "/tmp/log")
    assert "tool_calls" in row
    assert isinstance(row["tool_calls"], int)
    assert row["tool_calls"] == 5
