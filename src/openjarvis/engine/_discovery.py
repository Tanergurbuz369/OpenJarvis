"""Engine discovery — probe running engines and aggregate available models."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from openjarvis.core.config import JarvisConfig
from openjarvis.core.registry import EngineRegistry
from openjarvis.engine._base import InferenceEngine

logger = logging.getLogger(__name__)

# Map registry keys to config host attribute (None = no host arg)
_HOST_MAP: Dict[str, str | None] = {
    "ollama": "ollama_host",
    "vllm": "vllm_host",
    "llamacpp": "llamacpp_host",
    "sglang": "sglang_host",
    "mlx": "mlx_host",
    "lmstudio": "lmstudio_host",
    "exo": "exo_host",
    "nexa": "nexa_host",
    "uzu": "uzu_host",
    "apple_fm": "apple_fm_host",
    "lemonade": "lemonade_host",
    "cloud": None,
    "litellm": None,
    "gemma_cpp": None,
}


def _make_engine(key: str, config: JarvisConfig) -> InferenceEngine:
    """Instantiate a registered engine with the appropriate config host."""
    cls = EngineRegistry.get(key)

    # gemma_cpp: pass config fields instead of host
    if key == "gemma_cpp":
        cfg = config.engine.gemma_cpp
        return cls(
            model_path=cfg.model_path or None,
            tokenizer_path=cfg.tokenizer_path or None,
            model_type=cfg.model_type or None,
            num_threads=cfg.num_threads,
        )

    host_attr = _HOST_MAP.get(key)
    if host_attr is not None:
        host = getattr(config.engine, host_attr, None)
        if host:
            return cls(host=host)
    return cls()


def _maybe_register_mining_sidecar_engine() -> None:
    """If a mining sidecar exists with a ``vllm_endpoint``, register a derived
    vLLM engine class pointing at it.  Idempotent.  Quiet on error.

    The trigger is the *shape* of the sidecar (presence of ``vllm_endpoint``),
    not the value of its ``provider`` field — this leaves room for future
    non-engine-replacing providers (e.g., a hypothetical cpu-pearl) whose
    sidecars don't include ``vllm_endpoint``.
    """
    try:
        from openjarvis.mining import Sidecar
        from openjarvis.mining._constants import SIDECAR_PATH
    except ImportError:
        return

    if EngineRegistry.contains("vllm-pearl-mining"):
        return  # idempotent

    payload = Sidecar.read(SIDECAR_PATH)
    if payload is None:
        return

    endpoint = payload.get("vllm_endpoint")
    model = payload.get("model")
    if not endpoint or not model:
        return  # data-driven gate: no vllm_endpoint → don't register

    from openjarvis.engine._openai_compat import _OpenAICompatibleEngine

    # Strip a trailing "/v1" path segment so _default_host is the bare
    # base URL and _api_prefix="/v1" combines correctly in request paths.
    api_prefix = "/v1"
    base_url = endpoint.rstrip("/")
    if base_url.endswith(api_prefix):
        base_url = base_url[: -len(api_prefix)]

    _cls = type(
        "VllmPearlMiningEngine",
        (_OpenAICompatibleEngine,),
        {
            "engine_id": "vllm-pearl-mining",
            "_default_host": base_url,
            "_api_prefix": api_prefix,
        },
    )
    EngineRegistry.register_value("vllm-pearl-mining", _cls)


def discover_engines(config: JarvisConfig) -> List[Tuple[str, InferenceEngine]]:
    """Probe registered engines and return ``[(key, instance)]`` for healthy ones.

    Results are sorted with the config default engine first.
    """
    _maybe_register_mining_sidecar_engine()
    healthy: List[Tuple[str, InferenceEngine]] = []
    for key in EngineRegistry.keys():
        try:
            engine = _make_engine(key, config)
            if engine.health():
                healthy.append((key, engine))
        except Exception as exc:
            logger.debug("Engine %r failed during discovery: %s", key, exc)
            continue

    default_key = config.engine.default

    def sort_key(item: Tuple[str, Any]) -> Tuple[int, str]:
        return (0 if item[0] == default_key else 1, item[0])

    healthy.sort(key=sort_key)
    return healthy


def discover_models(
    engines: List[Tuple[str, InferenceEngine]],
) -> Dict[str, List[str]]:
    """Call ``list_models()`` on each engine and return a dict."""
    result: Dict[str, List[str]] = {}
    for key, engine in engines:
        try:
            result[key] = engine.list_models()
        except Exception as exc:
            logger.debug("Failed to list models for engine %r: %s", key, exc)
            result[key] = []
    return result


def get_failover_engine(config: JarvisConfig) -> Tuple[str, InferenceEngine] | None:
    """Build a FailoverEngine from ``config.intelligence.fallback_chain``.

    The chain is a comma-separated list of ``engine_key:model_id`` entries,
    e.g. ``"ollama:qwen3.5:9b,cloud:openrouter/deepseek/deepseek-chat-v3-0324:free"``.
    Splits on the *first* colon per entry so model ids that themselves
    contain colons (Ollama tags, OpenRouter's ``:free`` suffix) parse
    correctly. Entries with an unknown engine key, or whose engine fails to
    construct, are skipped with a warning rather than aborting the whole
    chain.

    Returns ``("failover", FailoverEngine(...))`` — matching ``get_engine()``'s
    return shape — or ``None`` if ``fallback_chain`` is unset or every entry
    was unusable.
    """
    spec = config.intelligence.fallback_chain
    if not spec:
        return None

    from openjarvis.engine.failover import FailoverEngine, Hop

    hops: list[Hop] = []
    for raw_entry in spec.split(","):
        entry = raw_entry.strip()
        if not entry or ":" not in entry:
            logger.warning("Skipping malformed fallback_chain entry: %r", raw_entry)
            continue
        engine_key, model_id = (part.strip() for part in entry.split(":", 1))
        if not engine_key or not model_id:
            logger.warning("Skipping malformed fallback_chain entry: %r", raw_entry)
            continue
        if not EngineRegistry.contains(engine_key):
            logger.warning(
                "Skipping fallback_chain entry with unknown engine %r: %r",
                engine_key,
                raw_entry,
            )
            continue
        try:
            engine = _make_engine(engine_key, config)
        except Exception as exc:
            logger.warning(
                "Failed to construct engine %r for fallback_chain entry %r: %s",
                engine_key,
                raw_entry,
                exc,
            )
            continue
        hops.append((engine_key, engine, model_id))

    if not hops:
        logger.warning(
            "fallback_chain %r produced no usable hops; ignoring", spec
        )
        return None
    return ("failover", FailoverEngine(hops))


def get_engine(
    config: JarvisConfig, engine_key: str | None = None
) -> Tuple[str, InferenceEngine] | None:
    """Get a specific engine by key, or the default with fallback.

    Returns ``(key, engine_instance)`` or ``None`` if no engine is available.
    """
    # Build an ordered list of keys to try, then fall back to full discovery.
    keys_to_try: list[str] = []
    if engine_key:
        keys_to_try.append(engine_key)

    default_key = config.engine.default
    if default_key and default_key not in keys_to_try:
        keys_to_try.append(default_key)

    for key in keys_to_try:
        if not EngineRegistry.contains(key):
            continue
        try:
            engine = _make_engine(key, config)
            if engine.health():
                return (key, engine)
        except Exception as exc:
            logger.debug("Engine %r health check failed: %s", key, exc)

    # Fallback to any healthy engine
    healthy = discover_engines(config)
    return healthy[0] if healthy else None


__all__ = [
    "discover_engines",
    "discover_models",
    "get_engine",
    "get_failover_engine",
]
