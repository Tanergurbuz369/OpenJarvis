"""Tests for Kimi (Moonshot AI) cloud provider support."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from openjarvis.core.registry import EngineRegistry
from openjarvis.core.types import Message, Role
from openjarvis.engine._base import EngineConnectionError
from openjarvis.engine.cloud import (
    _KIMI_MODELS,
    PRICING,
    CloudEngine,
    _is_kimi_model,
    estimate_cost,
)


def _make_cloud_engine(monkeypatch: pytest.MonkeyPatch) -> CloudEngine:
    """Create a CloudEngine with all API keys cleared."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    if not EngineRegistry.contains("cloud"):
        EngineRegistry.register_value("cloud", CloudEngine)
    return CloudEngine()


def _fake_kimi_response(
    content: str = "Hello from Kimi!",
    model: str = "kimi-k3",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    tool_calls: list | None = None,
) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestKimiRouting:
    def test_is_kimi_model(self) -> None:
        assert _is_kimi_model("kimi-k3") is True
        assert _is_kimi_model("Kimi-K3") is True
        assert _is_kimi_model("gpt-4o") is False
        assert _is_kimi_model("claude-opus-4-6") is False
        assert _is_kimi_model("MiniMax-M2.7") is False

    def test_kimi_models_list(self) -> None:
        assert "kimi-k3" in _KIMI_MODELS


# ---------------------------------------------------------------------------
# Init tests
# ---------------------------------------------------------------------------


class TestKimiInit:
    def test_init_with_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOONSHOT_API_KEY", "test-kimi-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        fake_openai = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"openai": fake_openai}):
            if not EngineRegistry.contains("cloud"):
                EngineRegistry.register_value("cloud", CloudEngine)
            engine = CloudEngine()
        assert engine._kimi_client is not None

    def test_health_with_kimi_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MOONSHOT_API_KEY", "test-kimi-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        fake_openai = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"openai": fake_openai}):
            engine = CloudEngine()
        assert engine.health() is True

    def test_no_kimi_key_no_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        assert engine._kimi_client is None


# ---------------------------------------------------------------------------
# Generate tests
# ---------------------------------------------------------------------------


class TestKimiGenerate:
    def test_k3_generate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.return_value = _fake_kimi_response(
            content="I am Kimi K3", model="kimi-k3"
        )
        engine._kimi_client = fake_client

        result = engine.generate(
            [Message(role=Role.USER, content="Hi")], model="kimi-k3"
        )
        assert result["content"] == "I am Kimi K3"
        assert result["model"] == "kimi-k3"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["cost_usd"] == pytest.approx(estimate_cost("kimi-k3", 10, 5))

    def test_uses_max_completion_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.return_value = _fake_kimi_response()
        engine._kimi_client = fake_client

        engine.generate(
            [Message(role=Role.USER, content="Hi")],
            model="kimi-k3",
            max_tokens=512,
        )
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 512
        assert "max_tokens" not in call_kwargs

    def test_reasoning_effort_passthrough(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = _make_cloud_engine(monkeypatch)
        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.return_value = _fake_kimi_response()
        engine._kimi_client = fake_client

        engine.generate(
            [Message(role=Role.USER, content="Hi")],
            model="kimi-k3",
            reasoning_effort="low",
        )
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["reasoning_effort"] == "low"

    def test_tool_calls_extraction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        fake_tool_call = SimpleNamespace(
            id="call_kimi_123",
            type="function",
            function=SimpleNamespace(name="search", arguments='{"q":"test"}'),
        )
        fake_resp = _fake_kimi_response(content="", model="kimi-k3")
        fake_resp.choices[0].message.tool_calls = [fake_tool_call]

        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.return_value = fake_resp
        engine._kimi_client = fake_client

        result = engine.generate(
            [Message(role=Role.USER, content="Search")], model="kimi-k3"
        )
        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["id"] == "call_kimi_123"
        assert tc["name"] == "search"

    def test_no_tool_calls_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        fake_client = mock.MagicMock()
        fake_client.chat.completions.create.return_value = _fake_kimi_response(
            content="Just text"
        )
        engine._kimi_client = fake_client

        result = engine.generate(
            [Message(role=Role.USER, content="Hi")], model="kimi-k3"
        )
        assert "tool_calls" not in result

    def test_no_client_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        assert engine._kimi_client is None

        with pytest.raises(EngineConnectionError, match="Kimi client not available"):
            engine.generate([Message(role=Role.USER, content="Hi")], model="kimi-k3")


# ---------------------------------------------------------------------------
# Model discovery tests
# ---------------------------------------------------------------------------


class TestKimiModelDiscovery:
    def test_list_models_includes_kimi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        engine._kimi_client = mock.MagicMock()
        models = engine.list_models()
        for m in _KIMI_MODELS:
            assert m in models

    def test_only_kimi_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        engine._kimi_client = mock.MagicMock()
        models = engine.list_models()
        assert set(models) == set(_KIMI_MODELS)


# ---------------------------------------------------------------------------
# Pricing tests
# ---------------------------------------------------------------------------


class TestKimiPricing:
    def test_kimi_k3_in_pricing(self) -> None:
        assert "kimi-k3" in PRICING

    def test_kimi_k3_cost_estimate(self) -> None:
        # kimi-k3: $3.00/M in (cache miss), $15.00/M out
        cost = estimate_cost("kimi-k3", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.00)

    def test_zero_tokens_zero_cost(self) -> None:
        assert estimate_cost("kimi-k3", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# Close tests
# ---------------------------------------------------------------------------


class TestKimiClose:
    def test_close_kimi_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _make_cloud_engine(monkeypatch)
        fake_client = mock.MagicMock()
        engine._kimi_client = fake_client
        engine.close()
        assert engine._kimi_client is None
        fake_client.close.assert_called_once()
