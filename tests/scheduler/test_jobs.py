"""Tests for the scheduler job registry and non-LLM job dispatch."""

from __future__ import annotations

import pytest

from openjarvis.scheduler import jobs
from openjarvis.scheduler.scheduler import TaskScheduler
from openjarvis.scheduler.store import SchedulerStore


def test_builtin_n8n_sync_resolves():
    fn = jobs.get_job("n8n_sync")
    assert callable(fn)
    assert fn.__name__ == "run_sync_job"


def test_unknown_job_raises():
    with pytest.raises(KeyError):
        jobs.get_job("does_not_exist")


def test_register_and_run_job():
    jobs.register_job("unit_test_job", lambda md: f"ok:{md.get('x')}")
    assert jobs.run_job("unit_test_job", {"x": 7}) == "ok:7"


def test_scheduler_dispatches_metadata_job(tmp_path, monkeypatch):
    calls = {}

    def fake_job(metadata):
        calls["metadata"] = metadata
        return "job-ran"

    monkeypatch.setitem(jobs._REGISTRY, "n8n_sync", fake_job)

    store = SchedulerStore(str(tmp_path / "s.db"))
    sched = TaskScheduler(store)  # system=None
    task = sched.create_task(
        "n8n sync",
        "interval",
        "3600",
        agent="n8n_sync",
        metadata={"job": "n8n_sync", "root": "/tmp/x", "install": False},
    )
    sched._execute_task(sched.list_tasks()[0])

    logs = store.get_run_logs(task.id)
    assert logs and logs[0]["success"] == 1
    assert logs[0]["result"] == "job-ran"
    assert calls["metadata"]["root"] == "/tmp/x"
    store.close()


def test_job_task_runs_without_system(tmp_path, monkeypatch):
    """A job task must run even when no JarvisSystem is attached."""
    monkeypatch.setitem(jobs._REGISTRY, "n8n_sync", lambda md: "no-system-ok")
    store = SchedulerStore(str(tmp_path / "s.db"))
    sched = TaskScheduler(store, system=None)
    task = sched.create_task(
        "sync", "interval", "60", agent="n8n_sync", metadata={"job": "n8n_sync"}
    )
    sched._execute_task(sched.list_tasks()[0])
    logs = store.get_run_logs(task.id)
    assert logs[0]["result"] == "no-system-ok"
    store.close()
