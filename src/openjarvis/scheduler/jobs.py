"""Registry of non-LLM scheduler *jobs*.

Most scheduled tasks run an agent prompt through ``system.ask``. Some tasks are
plain maintenance jobs (sync a catalog, prune caches, …) that should run a
Python callable instead. Such a task carries ``metadata["job"] = "<name>"`` and
the scheduler dispatches it here rather than to an agent.

A job is ``Callable[[dict], str]`` — it receives the task metadata and returns a
short human-readable result string that is stored in the run log.

Built-in jobs are registered lazily by dotted ``"module:function"`` path so the
scheduler package stays decoupled from feature packages (and avoids import
cycles). Extra jobs can be registered at runtime with :func:`register_job`.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, Dict

JobFn = Callable[[Dict[str, Any]], str]

# name -> "module:function"
BUILTIN_JOBS: Dict[str, str] = {
    "n8n_sync": "openjarvis.automations.n8n.jobs:run_sync_job",
}

_REGISTRY: Dict[str, JobFn] = {}


def register_job(name: str, fn: JobFn) -> None:
    """Register (or override) a job callable under *name*."""
    _REGISTRY[name] = fn


def _resolve(spec: str) -> JobFn:
    module_path, _, attr = spec.partition(":")
    module = importlib.import_module(module_path)
    fn = getattr(module, attr)
    if not callable(fn):  # pragma: no cover - defensive
        raise TypeError(f"job target is not callable: {spec}")
    return fn


def get_job(name: str) -> JobFn:
    """Return the callable for *name*, resolving a built-in if needed.

    Raises ``KeyError`` if the job is unknown.
    """
    if name in _REGISTRY:
        return _REGISTRY[name]
    if name in BUILTIN_JOBS:
        fn = _resolve(BUILTIN_JOBS[name])
        _REGISTRY[name] = fn  # cache
        return fn
    raise KeyError(f"Unknown scheduler job: {name}")


def run_job(name: str, metadata: Dict[str, Any]) -> str:
    """Resolve and execute the job *name* with *metadata*; return its result."""
    return get_job(name)(metadata or {})


__all__ = ["BUILTIN_JOBS", "get_job", "register_job", "run_job"]
