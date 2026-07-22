"""``jarvis n8n`` — mirror the n8n template library and auto-install workflows.

Commands:

- ``jarvis n8n sync``      index the upstream library into a local catalog
- ``jarvis n8n list``      show catalogued workflows
- ``jarvis n8n download``  fetch full workflow JSON into the local library
- ``jarvis n8n install``   turn new library workflows into agent templates
- ``jarvis n8n status``    show catalog / library / install state
- ``jarvis n8n schedule``  register a recurring sync+install on the scheduler
- ``jarvis n8n unschedule`` remove the scheduled sync task
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

DEFAULT_ROOT = Path("~/.openjarvis/n8n").expanduser()


def _sync(root: Path):
    from openjarvis.automations.n8n.sync import N8nLibrarySync

    return N8nLibrarySync(root)


@click.group()
def n8n() -> None:
    """Mirror the n8n template library and auto-install workflows as agents."""


@n8n.command("sync")
@click.option("--root", type=click.Path(), default=None, help="Catalog/library root.")
@click.option("--rows", default=100, show_default=True, help="Workflows per page.")
@click.option(
    "--max-pages",
    default=None,
    type=int,
    help="Limit pages fetched (omit for a full mirror of all workflows).",
)
@click.option("--search", default=None, help="Filter by search term.")
@click.option("--category", default=None, type=int, help="Filter by category id.")
def sync_cmd(
    root: Optional[str],
    rows: int,
    max_pages: Optional[int],
    search: Optional[str],
    category: Optional[int],
) -> None:
    """Index every page of the upstream library into ``catalog.json``."""
    console = Console(stderr=True)
    root_path = Path(root).expanduser() if root else DEFAULT_ROOT
    syncer = _sync(root_path)
    scope = "all pages" if max_pages is None else f"up to {max_pages} page(s)"
    console.print(f"[cyan]Syncing n8n catalog ({scope})…[/cyan]")
    with console.status("Fetching workflow metadata…") as status:

        def progress(done: int, total: int) -> None:
            status.update(f"Indexed {done}/{total or '?'} workflows…")

        catalog = syncer.sync_catalog(
            rows=rows,
            max_pages=max_pages,
            search=search,
            category=category,
            progress=progress,
        )
    syncer.close()
    console.print(
        f"[green]✓[/green] Catalog: [b]{len(catalog)}[/b] workflows indexed "
        f"({catalog.total_available} available upstream) → {syncer.catalog_path}"
    )


@n8n.command("list")
@click.option("--root", type=click.Path(), default=None, help="Catalog/library root.")
@click.option("--limit", default=25, show_default=True, help="Rows to display.")
@click.option("--search", default=None, help="Filter by name/description substring.")
def list_cmd(root: Optional[str], limit: int, search: Optional[str]) -> None:
    """List catalogued workflows (most viewed first)."""
    console = Console()
    root_path = Path(root).expanduser() if root else DEFAULT_ROOT
    catalog = _sync(root_path).load_catalog()
    if not catalog:
        console.print("[dim]Catalog is empty. Run 'jarvis n8n sync' first.[/dim]")
        return
    entries = catalog.sorted_entries()
    if search:
        needle = search.lower()
        entries = [
            e
            for e in entries
            if needle in e.name.lower() or needle in e.description.lower()
        ]
    table = Table(title=f"n8n workflows ({len(entries)} shown)")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Nodes", justify="right", style="green")
    table.add_column("Views", justify="right")
    table.add_column("Author")
    for e in entries[:limit]:
        table.add_row(
            str(e.id), e.name, str(e.nodes), f"{e.total_views:,}", e.author or "—"
        )
    console.print(table)


@n8n.command("download")
@click.option("--root", type=click.Path(), default=None, help="Catalog/library root.")
@click.option("--id", "workflow_id", type=int, default=None, help="Download one id.")
@click.option("--limit", type=int, default=None, help="Download top-N catalog entries.")
@click.option("--all", "download_all", is_flag=True, help="Download the whole catalog.")
def download_cmd(
    root: Optional[str],
    workflow_id: Optional[int],
    limit: Optional[int],
    download_all: bool,
) -> None:
    """Download full importable workflow JSON into the local library."""
    console = Console(stderr=True)
    root_path = Path(root).expanduser() if root else DEFAULT_ROOT
    syncer = _sync(root_path)
    if workflow_id is not None:
        path = syncer.download_workflow(workflow_id)
        syncer.close()
        console.print(f"[green]✓[/green] Downloaded → {path}")
        return
    n = None if download_all else (limit or 20)
    with console.status("Downloading workflows…") as status:

        def progress(done: int, total: int) -> None:
            status.update(f"Downloaded {done}/{total}…")

        paths = syncer.download_all(limit=n, progress=progress)
    syncer.close()
    console.print(f"[green]✓[/green] {len(paths)} workflow(s) in {syncer.library_dir}")


@n8n.command("install")
@click.option("--root", type=click.Path(), default=None, help="Catalog/library root.")
@click.option(
    "--templates-dir",
    type=click.Path(),
    default=None,
    help="Where to write generated agent templates (default ~/.openjarvis/templates).",
)
@click.option(
    "--from-catalog",
    "from_catalog",
    is_flag=True,
    default=False,
    help="Install every catalogued workflow (metadata only), not just library files.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="With --from-catalog, install only the top-N catalog entries.",
)
def install_cmd(
    root: Optional[str],
    templates_dir: Optional[str],
    from_catalog: bool,
    limit: Optional[int],
) -> None:
    """Install library workflows (or the whole catalog) as agent templates."""
    from openjarvis.automations.n8n.installer import N8nAutoInstaller

    console = Console(stderr=True)
    root_path = Path(root).expanduser() if root else DEFAULT_ROOT
    installer = N8nAutoInstaller(
        root_path / "library",
        templates_dir=Path(templates_dir).expanduser() if templates_dir else None,
    )
    if from_catalog:
        catalog = _sync(root_path).load_catalog()
        if not catalog:
            console.print("[dim]Catalog is empty. Run 'jarvis n8n sync' first.[/dim]")
            return
        with console.status("Installing catalogued workflows…"):
            results = installer.install_from_catalog(catalog, limit=limit)
    else:
        results = installer.install_new()

    if not results:
        console.print("[dim]Nothing new to install — everything up to date.[/dim]")
        return
    new = sum(1 for r in results if r.status == "installed")
    updated = sum(1 for r in results if r.status == "updated")
    console.print(
        f"[green]✓[/green] {new} new, {updated} updated → {installer.templates_dir}"
    )


@n8n.command("status")
@click.option("--root", type=click.Path(), default=None, help="Catalog/library root.")
def status_cmd(root: Optional[str]) -> None:
    """Show catalog, library, and install-manifest state."""
    from openjarvis.automations.n8n.installer import N8nAutoInstaller

    console = Console()
    root_path = Path(root).expanduser() if root else DEFAULT_ROOT
    syncer = _sync(root_path)
    catalog = syncer.load_catalog()
    library = list((root_path / "library").glob("*.workflow.json"))
    installer = N8nAutoInstaller(root_path / "library")
    pending = installer.pending()
    installed = installer.load_manifest()["installed"]

    table = Table(title="n8n integration status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")
    table.add_row("Root", str(root_path))
    table.add_row("Catalogued workflows", str(len(catalog)))
    table.add_row("Available upstream", str(catalog.total_available or "?"))
    table.add_row("Last synced", catalog.synced_at or "never")
    table.add_row("Downloaded to library", str(len(library)))
    table.add_row("Installed as templates", str(len(installed)))
    table.add_row("Pending install", str(len(pending)))
    console.print(table)


# The scheduler-task metadata marker for the recurring n8n sync job.
_JOB_NAME = "n8n_sync"


def _scheduler():
    """Build a (store, scheduler) pair from user config."""
    from openjarvis.core.config import DEFAULT_CONFIG_DIR, load_config
    from openjarvis.scheduler.scheduler import TaskScheduler
    from openjarvis.scheduler.store import SchedulerStore

    config = load_config()
    db_path = getattr(getattr(config, "scheduler", None), "db_path", None) or str(
        DEFAULT_CONFIG_DIR / "scheduler.db"
    )
    store = SchedulerStore(db_path)
    return store, TaskScheduler(store)


@n8n.command("schedule")
@click.option(
    "--cron",
    default="0 3 * * *",
    show_default=True,
    help="Cron expression (ignored if --interval is given).",
)
@click.option(
    "--interval",
    type=int,
    default=None,
    help="Run every N seconds instead of a cron schedule.",
)
@click.option("--root", type=click.Path(), default=None, help="Catalog/library root.")
@click.option("--max-pages", type=int, default=None, help="Limit pages fetched.")
@click.option(
    "--download-limit",
    type=int,
    default=None,
    help="Also download the top-N workflows each run.",
)
@click.option(
    "--no-install",
    is_flag=True,
    default=False,
    help="Only sync the catalog; do not auto-install workflows.",
)
def schedule_cmd(
    cron: str,
    interval: Optional[int],
    root: Optional[str],
    max_pages: Optional[int],
    download_limit: Optional[int],
    no_install: bool,
) -> None:
    """Register a recurring 'sync + auto-install' task on the scheduler.

    The task runs the built-in ``n8n_sync`` job (no LLM/agent), so it works
    whether the scheduler runs as a daemon (``jarvis scheduler start``) or is
    triggered on demand.
    """
    console = Console()
    metadata = {"job": _JOB_NAME, "install": not no_install}
    if root:
        metadata["root"] = str(Path(root).expanduser())
    if max_pages is not None:
        metadata["max_pages"] = max_pages
    if download_limit is not None:
        metadata["download_limit"] = download_limit

    if interval is not None:
        schedule_type, schedule_value = "interval", str(interval)
    else:
        schedule_type, schedule_value = "cron", cron

    store, sched = _scheduler()
    try:
        # Replace any existing n8n_sync task so scheduling is idempotent.
        removed = 0
        for t in sched.list_tasks():
            if (t.metadata or {}).get("job") == _JOB_NAME:
                store.delete_task(t.id)
                removed += 1
        task = sched.create_task(
            prompt="n8n library sync + auto-install",
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            agent=_JOB_NAME,
            metadata=metadata,
        )
    finally:
        store.close()

    if removed:
        console.print(f"[dim]Replaced {removed} existing n8n sync task(s).[/dim]")
    console.print(f"[green]✓[/green] Scheduled n8n sync (task {task.id})")
    console.print(f"  Schedule : {schedule_type} = {schedule_value}")
    console.print(f"  Install  : {'no' if no_install else 'yes'}")
    console.print(f"  Next run : {task.next_run or 'N/A'}")
    console.print(
        "[dim]Ensure the scheduler is running: 'jarvis scheduler start'.[/dim]"
    )


@n8n.command("unschedule")
def unschedule_cmd() -> None:
    """Remove the recurring n8n sync task from the scheduler."""
    console = Console()
    store, sched = _scheduler()
    try:
        removed = 0
        for t in sched.list_tasks():
            if (t.metadata or {}).get("job") == _JOB_NAME:
                store.delete_task(t.id)
                removed += 1
    finally:
        store.close()
    if removed:
        console.print(f"[green]✓[/green] Removed {removed} n8n sync task(s).")
    else:
        console.print("[dim]No scheduled n8n sync task found.[/dim]")
