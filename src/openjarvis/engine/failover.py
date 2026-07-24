"""Failover engine wrapper — advances through an ordered chain of hops.

Unlike ``MultiEngine`` (which routes a single named model to whichever
engine owns it), ``FailoverEngine`` wraps a fixed, ordered list of
``(label, engine, model)`` hops representing distinct model choices —
typically a free local model first, then one or more cloud fallbacks.
When a hop raises a retryable error (rate limit, timeout, connection
failure — see ``openjarvis.agents.errors.classify_error``), the request
is retried against the next hop instead of failing outright.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any, Dict, List, Tuple

from openjarvis.agents.errors import classify_error
from openjarvis.core.types import Message
from openjarvis.engine._stubs import InferenceEngine, StreamChunk

logger = logging.getLogger(__name__)

# A single failover hop: a human-readable label, the engine instance that
# serves it, and the specific model name to request from that engine.
Hop = Tuple[str, InferenceEngine, str]


class FailoverEngine(InferenceEngine):
    """Tries an ordered chain of ``(label, engine, model)`` hops in turn.

    The ``model`` keyword argument passed to ``generate()``/``stream()`` is
    accepted for interface compatibility with ``InferenceEngine`` but is
    otherwise ignored — each hop already carries its own fixed model.
    """

    engine_id = "failover"

    def __init__(self, chain: Sequence[Hop]) -> None:
        if not chain:
            raise ValueError(
                "FailoverEngine requires at least one (label, engine, model) hop"
            )
        self._chain: List[Hop] = list(chain)

    @property
    def chain(self) -> List[Hop]:
        return list(self._chain)

    def _hop_failed(self, index: int, label: str, model: str, exc: Exception) -> bool:
        """Log the failure and return True if the chain should advance."""
        is_last = index == len(self._chain) - 1
        classified = classify_error(exc)
        if is_last or not classified.retryable:
            return False
        logger.warning(
            "Failover: hop %d (%s/%s) failed (%s) — trying next hop",
            index,
            label,
            model,
            exc,
        )
        return True

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        last_exc: Exception = RuntimeError("FailoverEngine: empty chain")
        for i, (label, engine, hop_model) in enumerate(self._chain):
            try:
                result = engine.generate(
                    messages,
                    model=hop_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                if i > 0:
                    logger.info(
                        "Failover: served by hop %d (%s/%s) after "
                        "%d earlier failure(s)",
                        i,
                        label,
                        hop_model,
                        i,
                    )
                result.setdefault("_failover_hop", label)
                result.setdefault("_failover_model", hop_model)
                return result
            except Exception as exc:  # noqa: BLE001 - classified below
                last_exc = exc
                if not self._hop_failed(i, label, hop_model, exc):
                    raise
        raise last_exc

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        last_exc: Exception = RuntimeError("FailoverEngine: empty chain")
        for i, (label, engine, hop_model) in enumerate(self._chain):
            emitted_any = False
            try:
                async for token in engine.stream(
                    messages,
                    model=hop_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ):
                    emitted_any = True
                    yield token
                if i > 0:
                    logger.info(
                        "Failover: streamed by hop %d (%s/%s) after "
                        "%d earlier failure(s)",
                        i,
                        label,
                        hop_model,
                        i,
                    )
                return
            except Exception as exc:  # noqa: BLE001 - classified below
                last_exc = exc
                if emitted_any:
                    # Already sent partial output to the caller — switching
                    # hops now would corrupt the response, so surface the
                    # error instead of silently mixing two answers.
                    raise
                if not self._hop_failed(i, label, hop_model, exc):
                    raise
        raise last_exc

    async def stream_full(
        self,
        messages: Sequence[Message],
        *,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator["StreamChunk"]:
        last_exc: Exception = RuntimeError("FailoverEngine: empty chain")
        for i, (label, engine, hop_model) in enumerate(self._chain):
            emitted_any = False
            try:
                async for chunk in engine.stream_full(
                    messages,
                    model=hop_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                ):
                    emitted_any = True
                    yield chunk
                if i > 0:
                    logger.info(
                        "Failover: streamed by hop %d (%s/%s) after "
                        "%d earlier failure(s)",
                        i,
                        label,
                        hop_model,
                        i,
                    )
                return
            except Exception as exc:  # noqa: BLE001 - classified below
                last_exc = exc
                if emitted_any:
                    # Already sent partial output to the caller — switching
                    # hops now would corrupt the response, so surface the
                    # error instead of silently mixing two answers.
                    raise
                if not self._hop_failed(i, label, hop_model, exc):
                    raise
        raise last_exc

    def list_models(self) -> List[str]:
        """Return the primary (first-hop) model, representative of the chain."""
        return [self._chain[0][2]]

    def health(self) -> bool:
        return any(engine.health() for _label, engine, _model in self._chain)

    def close(self) -> None:
        seen: set[int] = set()
        for _label, engine, _model in self._chain:
            if id(engine) not in seen:
                seen.add(id(engine))
                engine.close()


__all__ = ["FailoverEngine", "Hop"]
