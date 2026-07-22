"""Auto-install n8n library workflows as OpenJarvis agent templates.

Dropping any ``*.workflow.json`` file into the library directory (whether from
``jarvis n8n sync``/``download`` or by hand) makes it *installable*. The
installer discovers workflows, and for every new or changed one it generates a
matching managed-agent template so OpenJarvis agents automatically recognize the
automation. Installation is idempotent: a manifest tracks a content hash per
workflow, so re-running only touches new or updated files.

By default, generated templates are written to ``~/.openjarvis/templates`` — the
same user-template directory that :meth:`AgentManager.list_templates` already
scans — so a freshly installed workflow shows up with no extra wiring.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_templates_dir() -> Path:
    return Path("~/.openjarvis/templates").expanduser()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _toml_basic_string(value: str) -> str:
    """Escape a value for a TOML basic (double-quoted) string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


def _toml_multiline(value: str) -> str:
    """Make *value* safe inside a TOML multiline basic string (triple quotes)."""
    # A backslash-escape run and stray triple quotes would break the literal.
    value = value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    # A multiline basic string cannot end with an unescaped quote.
    if value.endswith('"'):
        value = value[:-1] + '\\"'
    return value


@dataclass(slots=True)
class InstalledWorkflow:
    """Result of installing (or refreshing) one workflow."""

    workflow_file: str
    template_id: str
    template_path: str
    status: str  # "installed" | "updated" | "unchanged"


class N8nAutoInstaller:
    """Discover library workflows and install them as agent templates."""

    def __init__(
        self,
        library_dir: str | Path,
        *,
        templates_dir: Optional[str | Path] = None,
        manifest_path: Optional[str | Path] = None,
    ) -> None:
        self.library_dir = Path(library_dir)
        self.templates_dir = (
            Path(templates_dir) if templates_dir else _default_templates_dir()
        )
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path
            else self.library_dir.parent / "install_manifest.json"
        )

    # -- discovery -----------------------------------------------------
    def discover(self) -> List[Path]:
        """Return every ``*.workflow.json`` in the library, sorted by name."""
        if not self.library_dir.is_dir():
            return []
        return sorted(self.library_dir.glob("*.workflow.json"))

    def load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"installed": {}}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"installed": {}}
        data.setdefault("installed", {})
        return data

    def save_manifest(self, manifest: Dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def pending(self) -> List[Path]:
        """Workflows that are new or changed since the last install."""
        manifest = self.load_manifest()
        installed = manifest["installed"]
        out: List[Path] = []
        for path in self.discover():
            rec = installed.get(path.name)
            if rec is None or rec.get("hash") != self._hash(path):
                out.append(path)
        return out

    # -- installation --------------------------------------------------
    def install_new(self) -> List[InstalledWorkflow]:
        """Install every new/changed workflow as an agent template (idempotent)."""
        manifest = self.load_manifest()
        installed = manifest["installed"]
        results: List[InstalledWorkflow] = []
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        for path in self.discover():
            digest = self._hash(path)
            rec = installed.get(path.name)
            if rec is not None and rec.get("hash") == digest:
                continue
            status = "updated" if rec is not None else "installed"
            template_id, toml_text = self._render_template(path)
            template_path = self.templates_dir / f"{template_id}.toml"
            template_path.write_text(toml_text, encoding="utf-8")
            installed[path.name] = {
                "hash": digest,
                "template_id": template_id,
                "template_path": str(template_path),
                "installed_at": _utcnow_iso(),
            }
            results.append(
                InstalledWorkflow(
                    workflow_file=path.name,
                    template_id=template_id,
                    template_path=str(template_path),
                    status=status,
                )
            )
            logger.info("%s n8n workflow template: %s", status, template_id)
        self.save_manifest(manifest)
        return results

    # -- template rendering -------------------------------------------
    @staticmethod
    def _template_id(path: Path) -> str:
        stem = (
            path.name[: -len(".workflow.json")]
            if path.name.endswith(".workflow.json")
            else path.stem
        )
        slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
        return f"n8n_{slug}" if slug else "n8n_workflow"

    def _render_template(self, path: Path) -> tuple[str, str]:
        """Return ``(template_id, toml_text)`` for a workflow file."""
        graph = json.loads(path.read_text(encoding="utf-8"))
        name = graph.get("name") or path.stem
        nodes = graph.get("nodes") or []
        node_types = []
        for n in nodes:
            t = (n.get("type") or "").split(".")[-1]
            if t and t not in node_types:
                node_types.append(t)
        meta = graph.get("meta") or {}
        owner = meta.get("owner") or "n8n.io"
        template_id = self._template_id(path)

        summary_nodes = ", ".join(node_types[:12]) or "n8n nodes"
        trigger = next(
            (
                (n.get("type") or "").split(".")[-1]
                for n in nodes
                if "trigger" in (n.get("type") or "").lower()
            ),
            "manuel/webhook",
        )

        prompt = (
            f"Sen '{name}' adlı n8n otomasyonunu bilen bir OpenJarvis ajanısın. "
            f"Bu iş akışı n8n şablon kütüphanesinden içe aktarıldı "
            f"(sahip: {owner}).\n\n"
            f"## İş Akışı Özeti\n"
            f"- Tetikleyici: {trigger}\n"
            f"- Node sayısı: {len(nodes)}\n"
            f"- Kullanılan node türleri: {summary_nodes}\n\n"
            f"## Talimat\n{{instruction}}\n\n"
            f"## Görevin\n"
            f"1. Kullanıcının bu otomasyonu kurmasına, uyarlamasına ve "
            f"çalıştırmasına yardım et.\n"
            f"2. Gereken kimlik bilgilerini (credentials) ve kurulum "
            f"adımlarını açıkla.\n"
            f"3. İş akışını kullanıcının ihtiyacına göre nasıl "
            f"değiştireceğini anlat.\n"
            f"4. İlgili n8n JSON dosyası: {path.name}\n\n"
            f"Yanıtların kullanıcının dilinde olsun; teknik terimlerde n8n "
            f"terminolojisini koru."
        )

        description = (
            f"n8n kütüphanesinden içe aktarılan otomasyon: {name} "
            f"({len(nodes)} node). Sahip: {owner}."
        )

        toml_text = (
            "# Auto-generated by openjarvis.automations.n8n.installer.\n"
            "# Do not edit by hand — regenerate with `jarvis n8n install`.\n"
            f"# Source workflow: {path.name}\n\n"
            "[template]\n"
            f'id = "{_toml_basic_string(template_id)}"\n'
            f'name = "{_toml_basic_string(name)}"\n'
            f'description = "{_toml_basic_string(description)}"\n'
            'icon = "🔗"\n'
            'agent_type = "orchestrator"\n'
            'schedule_type = "manual"\n'
            'schedule_value = ""\n'
            'tools = ["web_search", "http_request", "think"]\n'
            "max_turns = 10\n"
            "temperature = 0.4\n"
            f'source = "n8n"\n'
            f'n8n_workflow_file = "{_toml_basic_string(path.name)}"\n'
            f'system_prompt_template = """{_toml_multiline(prompt)}"""\n'
        )
        return template_id, toml_text

    # -- catalog-based installation -----------------------------------
    @staticmethod
    def _entry_template_id(entry: Any) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", (entry.slug or "").lower()).strip("_")
        return f"n8n_{entry.id}_{slug}" if slug else f"n8n_{entry.id}"

    def _render_from_entry(self, entry: Any) -> tuple[str, str]:
        """Render a template from a catalog entry (metadata only, no full JSON)."""
        template_id = self._entry_template_id(entry)
        owner = entry.author or "n8n.io"
        cats = ", ".join(entry.categories) if entry.categories else "genel"
        prompt = (
            f"Sen '{entry.name}' adlı n8n otomasyonunu bilen bir OpenJarvis "
            f"ajanısın. Bu iş akışı n8n şablon kütüphanesinden geldi "
            f"(sahip: {owner}).\n\n"
            f"## İş Akışı Özeti\n"
            f"- Node sayısı: {entry.nodes}\n"
            f"- Kategoriler: {cats}\n"
            f"- Kaynak: {entry.url}\n\n"
            f"## Talimat\n{{instruction}}\n\n"
            f"## Görevin\n"
            f"1. Kullanıcının bu otomasyonu kurmasına, uyarlamasına ve "
            f"çalıştırmasına yardım et.\n"
            f"2. Gereken kimlik bilgilerini (credentials) ve kurulum "
            f"adımlarını açıkla.\n"
            f"3. Tam workflow JSON'u gerektiğinde `jarvis n8n download "
            f"--id {entry.id}` ile indirilebilir.\n\n"
            f"Yanıtların kullanıcının dilinde olsun; teknik terimlerde n8n "
            f"terminolojisini koru."
        )
        description = (
            f"n8n kütüphanesinden: {entry.name} ({entry.nodes} node). Sahip: {owner}."
        )
        toml_text = (
            "# Auto-generated by openjarvis.automations.n8n.installer.\n"
            "# Do not edit by hand — regenerate with `jarvis n8n install`.\n"
            f"# Source workflow id: {entry.id} ({entry.url})\n\n"
            "[template]\n"
            f'id = "{_toml_basic_string(template_id)}"\n'
            f'name = "{_toml_basic_string(entry.name)}"\n'
            f'description = "{_toml_basic_string(description)}"\n'
            'icon = "🔗"\n'
            'agent_type = "orchestrator"\n'
            'schedule_type = "manual"\n'
            'schedule_value = ""\n'
            'tools = ["web_search", "http_request", "think"]\n'
            "max_turns = 10\n"
            "temperature = 0.4\n"
            'source = "n8n"\n'
            f"n8n_workflow_id = {int(entry.id)}\n"
            f'n8n_url = "{_toml_basic_string(entry.url)}"\n'
            f'system_prompt_template = """{_toml_multiline(prompt)}"""\n'
        )
        return template_id, toml_text

    def install_from_catalog(
        self, catalog: Any, *, limit: Optional[int] = None
    ) -> List[InstalledWorkflow]:
        """Install a template for every catalogued workflow (metadata only).

        Idempotent: manifest entries are keyed by ``catalog:<id>`` and a content
        hash, so re-running only writes new or changed templates. This installs
        the entire indexed library without downloading each full workflow JSON.
        """
        manifest = self.load_manifest()
        installed = manifest["installed"]
        results: List[InstalledWorkflow] = []
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        entries = catalog.sorted_entries()
        if limit is not None:
            entries = entries[:limit]
        for entry in entries:
            template_id, toml_text = self._render_from_entry(entry)
            key = f"catalog:{entry.id}"
            digest = hashlib.sha256(toml_text.encode("utf-8")).hexdigest()
            rec = installed.get(key)
            if rec is not None and rec.get("hash") == digest:
                continue
            status = "updated" if rec is not None else "installed"
            template_path = self.templates_dir / f"{template_id}.toml"
            template_path.write_text(toml_text, encoding="utf-8")
            installed[key] = {
                "hash": digest,
                "template_id": template_id,
                "template_path": str(template_path),
                "installed_at": _utcnow_iso(),
            }
            results.append(
                InstalledWorkflow(
                    workflow_file=key,
                    template_id=template_id,
                    template_path=str(template_path),
                    status=status,
                )
            )
        self.save_manifest(manifest)
        logger.info("installed %d catalog templates", len(results))
        return results
