"""Tests for FailoverEngine — chain advancement on retryable errors."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Dict, List

import pytest

from openjarvis.core.types import Message, Role
from openjarvis.engine._stubs import InferenceEngine
from openjarvis.engine.failover import FailoverEngine

_MSGS = [Message(role=Role.USER, content="hi")]


class _FixedEngine(InferenceEngine):
    """Fake engine that always succeeds with a fixed response."""

    engine_id = "fixed"

    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0

    def generate(self, messages, *, model, **kwargs) -> Dict[str, Any]:
        self.calls += 1
        return {"content": f"reply from {self.label}", "usage": {}}

    async def stream(self, messages, *, model, **kwargs) -> AsyncIterator[str]:
        self.calls += 1
        yield f"tok-{self.label}"

    def list_models(self) -> List[str]:
        return [f"{self.label}-model"]

    def health(self) -> bool:
        return True


class _FailingEngine(InferenceEngine):
    """Fake engine that always raises a given exception."""

    engine_id = "failing"

    def __init__(self, exc: Exception, *, yield_before_fail: str | None = None) -> None:
        self._exc = exc
        self._yield_before_fail = yield_before_fail
        self.calls = 0

    def generate(self, messages, *, model, **kwargs) -> Dict[str, Any]:
        self.calls += 1
        raise self._exc

    async def stream(self, messages, *, model, **kwargs) -> AsyncIterator[str]:
        self.calls += 1
        if self._yield_before_fail is not None:
            yield self._yield_before_fail
        raise self._exc
        yield ""  # pragma: no cover - unreachable, satisfies generator shape

    def list_models(self) -> List[str]:
        return ["failing-model"]

    def health(self) -> bool:
        return False


def _rate_limited() -> Exception:
    return RuntimeError("429 Too Many Requests: rate limit exceeded")


def _unauthorized() -> Exception:
    return RuntimeError("401 Unauthorized: invalid api key")


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


def test_generate_uses_first_hop_when_healthy():
    primary = _FixedEngine("local")
    chain = [("ollama", primary, "local-model")]
    engine = FailoverEngine(chain)

    result = engine.generate(_MSGS, model="ignored")

    assert result["content"] == "reply from local"
    assert result["_failover_hop"] == "ollama"
    assert primary.calls == 1


def test_generate_advances_to_next_hop_on_rate_limit():
    primary = _FailingEngine(_rate_limited())
    secondary = _FixedEngine("cloud")
    chain = [
        ("ollama", primary, "local-model"),
        ("openrouter", secondary, "deepseek/deepseek-chat-v3-0324:free"),
    ]
    engine = FailoverEngine(chain)

    result = engine.generate(_MSGS, model="ignored")

    assert result["content"] == "reply from cloud"
    assert result["_failover_hop"] == "openrouter"
    assert primary.calls == 1
    assert secondary.calls == 1


def test_generate_raises_last_error_when_all_hops_fail():
    exc1 = _rate_limited()
    exc2 = RuntimeError("503 Service Unavailable")
    chain = [
        ("ollama", _FailingEngine(exc1), "local-model"),
        ("openrouter", _FailingEngine(exc2), "cloud-model"),
    ]
    engine = FailoverEngine(chain)

    with pytest.raises(RuntimeError, match="503"):
        engine.generate(_MSGS, model="ignored")


def test_generate_does_not_fail_over_on_fatal_auth_error():
    """An invalid API key shouldn't be masked by silently trying the next hop."""
    primary = _FailingEngine(_unauthorized())
    secondary = _FixedEngine("cloud")
    chain = [
        ("openrouter", primary, "bad-key-model"),
        ("backup", secondary, "backup-model"),
    ]
    engine = FailoverEngine(chain)

    with pytest.raises(RuntimeError, match="401"):
        engine.generate(_MSGS, model="ignored")
    assert secondary.calls == 0


def test_generate_empty_chain_rejected():
    with pytest.raises(ValueError):
        FailoverEngine([])


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_advances_to_next_hop_before_any_token_emitted():
    primary = _FailingEngine(_rate_limited())  # fails before yielding anything
    secondary = _FixedEngine("cloud")
    chain = [
        ("ollama", primary, "local-model"),
        ("openrouter", secondary, "cloud-model"),
    ]
    engine = FailoverEngine(chain)

    tokens = [t async for t in engine.stream(_MSGS, model="ignored")]

    assert tokens == ["tok-cloud"]


@pytest.mark.asyncio
async def test_stream_does_not_switch_hops_after_partial_output():
    """Once tokens reach the caller, failing over would corrupt the response."""
    primary = _FailingEngine(_rate_limited(), yield_before_fail="partial")
    secondary = _FixedEngine("cloud")
    chain = [
        ("ollama", primary, "local-model"),
        ("openrouter", secondary, "cloud-model"),
    ]
    engine = FailoverEngine(chain)

    collected = []
    with pytest.raises(RuntimeError, match="429"):
        async for tok in engine.stream(_MSGS, model="ignored"):
            collected.append(tok)

    assert collected == ["partial"]
    assert secondary.calls == 0


# ---------------------------------------------------------------------------
# list_models() / health() / close()
# ---------------------------------------------------------------------------


def test_list_models_returns_primary_hop_model():
    chain = [
        ("ollama", _FixedEngine("local"), "qwen3.5:9b"),
        ("openrouter", _FixedEngine("cloud"), "deepseek/deepseek-chat-v3-0324:free"),
    ]
    engine = FailoverEngine(chain)

    assert engine.list_models() == ["qwen3.5:9b"]


def test_health_true_if_any_hop_healthy():
    chain = [
        ("ollama", _FailingEngine(_rate_limited()), "local-model"),
        ("openrouter", _FixedEngine("cloud"), "cloud-model"),
    ]
    engine = FailoverEngine(chain)

    assert engine.health() is True
