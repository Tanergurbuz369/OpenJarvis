"""Structural validation for the importable n8n workflow JSON files.

These tests do not run n8n; they assert that every ``*.workflow.json`` under
``automations/n8n`` is importable-shaped: valid JSON, well-formed nodes, and
connections that reference existing nodes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

N8N_DIR = Path(__file__).resolve().parents[2] / "automations" / "n8n"


def _workflow_files() -> List[Path]:
    return sorted(N8N_DIR.glob("*.workflow.json"))


def test_n8n_directory_exists() -> None:
    assert N8N_DIR.is_dir(), f"missing automations/n8n dir: {N8N_DIR}"


def test_at_least_one_workflow() -> None:
    assert _workflow_files(), "no *.workflow.json files found under automations/n8n"


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_workflow_is_valid(path: Path) -> None:
    """Each workflow parses and has n8n's required top-level shape."""
    wf = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(wf.get("name"), str) and wf["name"], "workflow needs a name"
    nodes = wf.get("nodes")
    assert isinstance(nodes, list) and nodes, "workflow needs a non-empty nodes list"
    assert isinstance(wf.get("connections"), dict), "connections must be an object"

    names: List[str] = []
    for node in nodes:
        for key in ("name", "type", "typeVersion", "position"):
            assert key in node, f"node missing '{key}': {node.get('name')}"
        assert isinstance(node["type"], str) and node["type"].startswith(
            "n8n-nodes-base."
        ), f"unexpected node type: {node['type']}"
        assert isinstance(node["position"], list) and len(node["position"]) == 2, (
            f"node position must be [x, y]: {node['name']}"
        )
        names.append(node["name"])

    assert len(names) == len(set(names)), "duplicate node names in workflow"

    # Must contain at least one trigger node.
    assert any(
        "trigger" in n["type"].lower() or n["type"].endswith("webhook") for n in nodes
    ), "workflow has no trigger node"

    # Every connection endpoint must reference an existing node.
    name_set = set(names)
    connections: Dict = wf["connections"]
    for source, conf in connections.items():
        assert source in name_set, f"connection from unknown node: {source}"
        for outputs in conf.get("main", []):
            for link in outputs:
                assert link["node"] in name_set, (
                    f"dangling connection to unknown node: {link['node']}"
                )


def test_daily_ai_briefing_specifics() -> None:
    """The daily briefing workflow keeps its key wiring and ownership."""
    path = N8N_DIR / "daily_ai_briefing.workflow.json"
    assert path.exists(), "daily_ai_briefing.workflow.json is missing"
    wf = json.loads(path.read_text(encoding="utf-8"))

    types = {n["type"] for n in wf["nodes"]}
    assert "n8n-nodes-base.scheduleTrigger" in types
    assert "n8n-nodes-base.httpRequest" in types
    assert "n8n-nodes-base.slack" in types

    # HTTP node should have retry/error handling configured.
    http = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest")
    assert http.get("retryOnFail") is True
    assert http.get("onError") == "continueErrorOutput"

    assert wf.get("meta", {}).get("owner") == "Mert Durmazer"
