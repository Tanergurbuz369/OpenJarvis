"""Tests for the n8n auto-installer (workflows -> agent templates)."""

from __future__ import annotations

import json
from pathlib import Path

import tomllib

from openjarvis.automations.n8n.installer import (
    N8nAutoInstaller,
    _toml_basic_string,
    _toml_multiline,
)


def _write_workflow(library: Path, wid: int, name: str, owner: str = "n8n.io") -> Path:
    wf = {
        "name": name,
        "nodes": [
            {"type": "n8n-nodes-base.webhook", "name": "Hook"},
            {"type": "n8n-nodes-base.httpRequest", "name": "HTTP"},
            {"type": "@n8n/n8n-nodes-langchain.agent", "name": "Agent"},
        ],
        "connections": {},
        "meta": {"owner": owner},
    }
    path = library / f"{wid}-{name.lower().replace(' ', '-')}.workflow.json"
    path.write_text(json.dumps(wf), encoding="utf-8")
    return path


def _installer(tmp_path: Path) -> N8nAutoInstaller:
    library = tmp_path / "library"
    library.mkdir()
    return N8nAutoInstaller(
        library,
        templates_dir=tmp_path / "templates",
        manifest_path=tmp_path / "manifest.json",
    )


def test_install_generates_valid_template(tmp_path):
    inst = _installer(tmp_path)
    _write_workflow(inst.library_dir, 7, "Cool Bot", owner="Mert Durmazer")

    results = inst.install_new()
    assert len(results) == 1
    r = results[0]
    assert r.template_id == "n8n_7_cool_bot"
    assert r.status == "installed"

    tpl_path = Path(r.template_path)
    data = tomllib.loads(tpl_path.read_text(encoding="utf-8"))["template"]
    assert data["id"] == "n8n_7_cool_bot"
    assert data["name"] == "Cool Bot"
    assert data["agent_type"] == "orchestrator"
    assert data["source"] == "n8n"
    assert "{instruction}" in data["system_prompt_template"]
    assert "Mert Durmazer" in data["system_prompt_template"]


def test_install_is_idempotent(tmp_path):
    inst = _installer(tmp_path)
    _write_workflow(inst.library_dir, 1, "One")
    assert len(inst.install_new()) == 1
    assert inst.install_new() == []  # nothing new the second time
    assert inst.pending() == []


def test_pending_detects_new_and_changed(tmp_path):
    inst = _installer(tmp_path)
    p = _write_workflow(inst.library_dir, 1, "One")
    inst.install_new()

    # add a new workflow -> pending
    _write_workflow(inst.library_dir, 2, "Two")
    pending_names = {x.name for x in inst.pending()}
    assert any("2-two" in n for n in pending_names)

    # change an existing workflow -> becomes pending again
    data = json.loads(p.read_text())
    data["name"] = "One Renamed"
    p.write_text(json.dumps(data), encoding="utf-8")
    pending_names = {x.name for x in inst.pending()}
    assert p.name in pending_names

    results = inst.install_new()
    statuses = {r.template_id: r.status for r in results}
    assert statuses["n8n_1_one"] == "updated"
    assert statuses["n8n_2_two"] == "installed"


def test_agent_manager_discovers_installed_template(tmp_path, monkeypatch):
    """A generated template placed in the user dir is discovered + instantiable."""
    from openjarvis.agents.manager import AgentManager

    home = tmp_path / "home"
    (home / ".openjarvis" / "templates").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    library = tmp_path / "library"
    library.mkdir()
    inst = N8nAutoInstaller(library)  # defaults to ~/.openjarvis/templates
    _write_workflow(library, 99, "Discover Me")
    installed = inst.install_new()
    assert installed and installed[0].template_id == "n8n_99_discover_me"

    ids = [t.get("id") for t in AgentManager.list_templates()]
    assert "n8n_99_discover_me" in ids

    mgr = AgentManager(db_path=str(tmp_path / "agents.db"))
    agent = mgr.create_from_template(
        "n8n_99_discover_me", "Test", overrides={"instruction": "hedef görev"}
    )
    assert "hedef görev" in agent["config"]["system_prompt"]
    mgr.close()


def test_toml_escaping_helpers():
    assert _toml_basic_string('a "b" c') == 'a \\"b\\" c'
    assert '"""' not in _toml_multiline('x """ y')
    assert _toml_multiline('ends with quote"').endswith('\\"')


def _catalog(n=3):
    from openjarvis.automations.n8n.catalog import Catalog, CatalogEntry

    cat = Catalog(total_available=n)
    for i in range(1, n + 1):
        cat.upsert(
            CatalogEntry.from_api(
                {
                    "id": i,
                    "name": f"Workflow {i}",
                    "description": "d",
                    "user": {"name": "Owner"},
                    "nodes": [{"type": "n8n-nodes-base.set"}] * i,
                    "totalViews": i * 10,
                }
            )
        )
    return cat


def test_install_from_catalog_generates_all(tmp_path):
    inst = _installer(tmp_path)
    cat = _catalog(3)
    results = inst.install_from_catalog(cat)
    assert len(results) == 3
    ids = {r.template_id for r in results}
    assert "n8n_3_workflow_3" in ids
    # every template file exists and is valid TOML with the workflow id + url
    for r in results:
        data = tomllib.loads(Path(r.template_path).read_text(encoding="utf-8"))
        tpl = data["template"]
        assert tpl["source"] == "n8n"
        assert isinstance(tpl["n8n_workflow_id"], int)
        assert tpl["n8n_url"].startswith("https://n8n.io/workflows/")
        assert "{instruction}" in tpl["system_prompt_template"]


def test_install_from_catalog_is_idempotent(tmp_path):
    inst = _installer(tmp_path)
    cat = _catalog(4)
    assert len(inst.install_from_catalog(cat)) == 4
    assert inst.install_from_catalog(cat) == []  # nothing new the second time


def test_install_from_catalog_respects_limit(tmp_path):
    inst = _installer(tmp_path)
    cat = _catalog(5)
    results = inst.install_from_catalog(cat, limit=2)
    assert len(results) == 2
    # most-viewed first: ids 5 and 4
    assert {r.template_id for r in results} == {"n8n_5_workflow_5", "n8n_4_workflow_4"}
