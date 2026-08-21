"""``jarvis connect`` -- manage data source connections."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table


def _list_sources(registry: object) -> None:
    """Print a Rich table of registered connectors and their sync status."""
    console = Console()
    items = registry.items()  # type: ignore[attr-defined]

    if not items:
        console.print("[yellow]No connectors registered.[/yellow]")
        return

    table = Table(title="Connected Sources")
    table.add_column("Source", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Status", style="green")

    for key, connector_cls in items:
        # Try to instantiate with no args to check status (best-effort)
        try:
            instance = connector_cls()
            connected = instance.is_connected()
            status = "connected" if connected else "disconnected"
            auth_type = getattr(connector_cls, "auth_type", "unknown")
        except Exception:  # noqa: BLE001
            status = "unknown"
            auth_type = getattr(connector_cls, "auth_type", "unknown")

        table.add_row(key, auth_type, status)

    try:
        from openjarvis.connectors.oauth import list_google_accounts

        for profile in list_google_accounts():
            status = (
                "disabled"
                if not profile.get("enabled", True)
                else "connected"
                if profile["connected"]
                else "pending"
            )
            table.add_row(f"google:{profile['account']}", "oauth", status)
    except Exception:  # noqa: BLE001
        pass

    console.print(table)


def _disconnect_source(registry: object, source: str, account: str = "") -> None:
    """Find and disconnect a registered source connector."""
    console = Console()

    if account:
        from openjarvis.connectors.oauth import (
            delete_tokens,
            get_provider_for_connector,
            google_account_credentials_path,
        )

        provider = get_provider_for_connector(source)
        if source == "google" or (provider and provider.name == "google"):
            try:
                _purge_google_account_index(account)
                delete_tokens(google_account_credentials_path(account))
                console.print(
                    f"[green]Disconnected Google account {account} from all "
                    "Google connectors.[/green]"
                )
            except Exception as exc:  # noqa: BLE001
                console.print(
                    f"[red]Failed to disconnect Google account {account}: {exc}[/red]"
                )
            return

    if not registry.contains(source):  # type: ignore[attr-defined]
        console.print(f"[red]Unknown source: {source}[/red]")
        return

    connector_cls = registry.get(source)  # type: ignore[attr-defined]
    try:
        try:
            instance = connector_cls(account=account) if account else connector_cls()
        except TypeError:
            instance = connector_cls()
        instance.disconnect()
        suffix = f":{account}" if account else ""
        console.print(f"[green]Disconnected {source}{suffix}.[/green]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to disconnect {source}: {exc}[/red]")


def _purge_google_account_index(account: str) -> None:
    """Remove all indexed rows/checkpoints owned by one Google profile."""
    from openjarvis.connectors.oauth import OAUTH_PROVIDERS
    from openjarvis.connectors.pipeline import IngestionPipeline
    from openjarvis.connectors.store import KnowledgeStore
    from openjarvis.connectors.sync_engine import SyncEngine

    connector_ids = tuple(OAUTH_PROVIDERS["google"].connector_ids)
    checkpoint_ids = tuple(
        f"{connector_id}:{account}" for connector_id in connector_ids
    )
    with KnowledgeStore() as store:
        with SyncEngine(pipeline=IngestionPipeline(store=store)) as engine:
            old_checkpoints = {
                key: engine.get_checkpoint(key) for key in checkpoint_ids
            }
            try:
                for key in checkpoint_ids:
                    engine.reset_checkpoint(key)
                store.delete_by_sources(connector_ids, account=account)
            except Exception:
                for key, checkpoint in old_checkpoints.items():
                    engine.restore_checkpoint(key, checkpoint)
                raise


def _migrate_legacy_google_index(account: str) -> None:
    """Remove unscoped legacy Google rows/checkpoints before named reindexing."""
    from openjarvis.connectors.oauth import OAUTH_PROVIDERS
    from openjarvis.connectors.pipeline import IngestionPipeline
    from openjarvis.connectors.store import KnowledgeStore
    from openjarvis.connectors.sync_engine import SyncEngine

    connector_ids = tuple(OAUTH_PROVIDERS["google"].connector_ids)
    unambiguous_sources = tuple(cid for cid in connector_ids if cid != "gmail")
    with KnowledgeStore() as store:
        with SyncEngine(pipeline=IngestionPipeline(store=store)) as engine:
            old_checkpoints = {
                connector_id: engine.get_checkpoint(connector_id)
                for connector_id in connector_ids
            }
            try:
                for connector_id in connector_ids:
                    engine.reset_checkpoint(connector_id)
                # Gmail OAuth and Gmail IMAP historically shared
                # ``source='gmail'``.  Delete Gmail rows only when they carry
                # positive Google-connector provenance; an unmarked row is
                # ambiguous and must be preserved rather than risking an
                # unrelated IMAP mailbox.  The other Google source IDs are
                # unambiguous and safe to migrate by source alone.
                store.delete_by_sources(unambiguous_sources, unscoped_only=True)
                store.delete_by_sources(
                    ("gmail",),
                    unscoped_only=True,
                    metadata_connector="gmail",
                )
            except Exception:
                for connector_id, checkpoint in old_checkpoints.items():
                    engine.restore_checkpoint(connector_id, checkpoint)
                raise


def _sync_sources(registry: object, source: str = "", account: str = "") -> None:
    """Run an incremental connector sync from the CLI."""
    from openjarvis.connectors.oauth import OAUTH_PROVIDERS
    from openjarvis.connectors.pipeline import IngestionPipeline
    from openjarvis.connectors.store import KnowledgeStore
    from openjarvis.connectors.sync_engine import SyncEngine

    console = Console()
    if source == "google":
        source_ids = list(OAUTH_PROVIDERS["google"].connector_ids)
    elif source:
        source_ids = [source]
    else:
        source_ids = list(registry.keys())  # type: ignore[attr-defined]

    with KnowledgeStore() as store:
        with SyncEngine(pipeline=IngestionPipeline(store=store)) as engine:
            for connector_id in source_ids:
                if not registry.contains(connector_id):  # type: ignore[attr-defined]
                    console.print(
                        f"[yellow]Skipping unknown source {connector_id}.[/yellow]"
                    )
                    continue
                connector_cls = registry.get(connector_id)  # type: ignore[attr-defined]
                try:
                    instance = (
                        connector_cls(account=account) if account else connector_cls()
                    )
                except (TypeError, ValueError) as exc:
                    console.print(
                        f"[yellow]Skipping {connector_id}: "
                        f"cannot configure ({exc}).[/yellow]"
                    )
                    continue
                if not instance.is_connected():
                    suffix = f":{account}" if account else ""
                    console.print(
                        f"[yellow]Skipping disconnected "
                        f"{connector_id}{suffix}.[/yellow]"
                    )
                    continue
                try:
                    count = engine.sync(instance)
                    suffix = f":{account}" if account else ""
                    console.print(
                        f"[green]Synced {connector_id}{suffix}: "
                        f"{count} document(s).[/green]"
                    )
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]Sync failed for {connector_id}: {exc}[/red]")


def _connect_source(
    registry: object,
    source: str,
    path: str = "",
    account: str = "",
) -> bool:
    """Route connector setup by auth_type."""
    console = Console()

    if source == "google":
        from openjarvis.connectors.oauth import (
            OAUTH_PROVIDERS,
            get_client_credentials,
            run_connector_oauth,
            save_client_credentials,
        )

        try:
            from openjarvis.connectors.gmail import GmailConnector

            if account and GmailConnector(account=account).is_connected():
                console.print(f"[green]google:{account} is already connected.[/green]")
                return True
            provider = OAUTH_PROVIDERS["google"]
            creds = get_client_credentials(provider, account=account)
            client_id = creds[0] if creds else ""
            client_secret = creds[1] if creds else ""

            if not client_id or not client_secret:
                console.print("[cyan]First-time setup for Google.[/cyan]")
                console.print(
                    f"[yellow]Create an OAuth app at: {provider.setup_url}[/yellow]"
                )
                console.print(f"[dim]{provider.setup_hint}[/dim]")
                client_id = click.prompt("Client ID")
                client_secret = click.prompt("Client Secret")
                save_client_credentials(
                    provider,
                    client_id,
                    client_secret,
                    account=account,
                )

            run_connector_oauth(
                "gmail",
                client_id,
                client_secret,
                account=account,
            )
            suffix = f":{account}" if account else ""
            console.print(f"[green]google{suffix} authorised successfully.[/green]")
            return True
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]OAuth flow failed for google: {exc}[/red]")
            return False

    if not registry.contains(source):  # type: ignore[attr-defined]
        console.print(f"[red]Unknown source: {source}[/red]")
        console.print(
            "[yellow]Available sources: "
            + ", ".join(registry.keys())  # type: ignore[attr-defined]
            + "[/yellow]"
        )
        return False

    connector_cls = registry.get(source)  # type: ignore[attr-defined]
    auth_type = getattr(connector_cls, "auth_type", "")

    if auth_type == "filesystem":
        # Filesystem connectors (e.g. Obsidian) need a path
        if not path:
            console.print(
                f"[red]{source} requires a --path argument (e.g. --path ~/vault).[/red]"
            )
            return False
        try:
            instance = connector_cls(vault_path=path)
        except TypeError:
            try:
                instance = connector_cls(path)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Failed to create {source} connector: {exc}[/red]")
                return False

        if instance.is_connected():
            console.print(f"[green]{source} connected at path: {path}[/green]")
            return True
        else:
            console.print(
                f"[red]{source}: path '{path}' does not exist or is not accessible."
                "[/red]"
            )
            return False

    elif auth_type == "oauth":
        # OAuth connectors — auto-open browser + catch callback
        from openjarvis.connectors.oauth import (
            get_client_credentials,
            get_provider_for_connector,
            run_connector_oauth,
            save_client_credentials,
        )

        try:
            try:
                instance = (
                    connector_cls(account=account) if account else connector_cls()
                )
            except TypeError:
                instance = connector_cls()
            if instance.is_connected():
                suffix = f":{account}" if account else ""
                console.print(f"[green]{source}{suffix} is already connected.[/green]")
                return True

            provider = get_provider_for_connector(source)
            if provider is None:
                console.print(f"[red]No OAuth provider configured for {source}.[/red]")
                return False

            creds = get_client_credentials(provider, account=account)
            client_id = creds[0] if creds else ""
            client_secret = creds[1] if creds else ""

            if not client_id or not client_secret:
                console.print(f"[cyan]First-time setup for {source}.[/cyan]")
                console.print(
                    f"[yellow]Create an OAuth app at: {provider.setup_url}[/yellow]"
                )
                console.print(f"[dim]{provider.setup_hint}[/dim]")
                client_id = click.prompt("Client ID")
                client_secret = click.prompt("Client Secret")
                save_client_credentials(
                    provider,
                    client_id,
                    client_secret,
                    account=account,
                )

            run_connector_oauth(source, client_id, client_secret, account=account)
            suffix = f":{account}" if account else ""
            console.print(f"[green]{source}{suffix} authorised successfully.[/green]")
            return True
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]OAuth flow failed for {source}: {exc}[/red]")
            return False

    elif auth_type == "token":
        # Token-based connectors (e.g. Oura) — prompt for personal access token
        import json
        from pathlib import Path

        from openjarvis.connectors.oauth import save_tokens
        from openjarvis.core.config import DEFAULT_CONFIG_DIR

        try:
            instance = connector_cls()
            if instance.is_connected():
                console.print(f"[green]{source} is already connected.[/green]")
                return True

            token = click.prompt(f"Enter your {source} personal access token")
            token_dir = Path(DEFAULT_CONFIG_DIR) / "connectors"
            token_dir.mkdir(parents=True, exist_ok=True)
            token_file = token_dir / f"{source}.json"
            token_file.write_text(json.dumps({"token": token}))
            save_tokens(source, {"token": token})
            console.print(f"[green]{source} connected successfully.[/green]")
            return True
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Token setup failed for {source}: {exc}[/red]")
            return False

    else:
        # Generic / bridge connectors
        try:
            instance = connector_cls()
            connected = instance.is_connected()
            status = "connected" if connected else "disconnected"
            console.print(f"{source} status: {status}")
            return connected
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Failed to connect {source}: {exc}[/red]")
            return False


@click.group(invoke_without_command=True)
@click.argument("source", required=False)
@click.option(
    "--list",
    "list_sources",
    is_flag=True,
    help="List connected sources and sync status.",
)
@click.option(
    "--sync",
    "trigger_sync",
    is_flag=True,
    help="Trigger incremental sync for all sources.",
)
@click.option(
    "--disconnect",
    "disconnect_source",
    default="",
    help="Disconnect a source.",
)
@click.option(
    "--path",
    default="",
    help="Path for filesystem connectors (e.g., Obsidian vault).",
)
@click.option(
    "--account",
    default="",
    help="Named connector account alias (e.g., personal, work).",
)
@click.option(
    "--profile",
    default="",
    help="Alias for --account.",
)
@click.option(
    "--migrate-legacy-google",
    is_flag=True,
    help=(
        "Delete unscoped legacy Google index rows/checkpoints before "
        "reindexing them into --account."
    ),
)
@click.pass_context
def connect(
    ctx: click.Context,
    source: str | None,
    list_sources: bool,
    trigger_sync: bool,
    disconnect_source: str,
    path: str,
    account: str,
    profile: str,
    migrate_legacy_google: bool,
) -> None:
    """Manage data source connections (Gmail, Obsidian, etc.)."""
    # Lazy imports to avoid top-level side effects
    import openjarvis.connectors  # noqa: F401 — registers all connectors
    from openjarvis.connectors.oauth import (
        get_provider_for_connector,
        normalize_account_alias,
    )
    from openjarvis.core.config import load_config
    from openjarvis.core.registry import ConnectorRegistry

    try:
        account_alias = normalize_account_alias(account)
        profile_alias = normalize_account_alias(profile)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    if account_alias and profile_alias and account_alias != profile_alias:
        raise click.UsageError("--account and --profile must name the same alias")
    account_alias = account_alias or profile_alias
    if (
        account_alias
        and not disconnect_source
        and not load_config().connectors.google.is_enabled(account_alias)
    ):
        raise click.UsageError(
            f"Google account profile '{account_alias}' is disabled in config.toml"
        )

    selected_source = disconnect_source or source or ""
    if account_alias and selected_source != "google":
        provider = get_provider_for_connector(selected_source)
        if provider is None or provider.name != "google":
            raise click.UsageError(
                "Named account profiles are currently supported only for Google "
                "connectors."
            )

    if list_sources:
        _list_sources(ConnectorRegistry)
        return

    if migrate_legacy_google:
        if not account_alias or selected_source != "google":
            raise click.UsageError(
                "--migrate-legacy-google requires `google --account ALIAS`"
            )

    if disconnect_source:
        _disconnect_source(ConnectorRegistry, disconnect_source, account=account_alias)
        return

    if source:
        connect_succeeded = _connect_source(
            ConnectorRegistry,
            source,
            path=path,
            account=account_alias,
        )
        if migrate_legacy_google:
            from openjarvis.connectors.gmail import GmailConnector

            if (
                not connect_succeeded
                or not GmailConnector(account=account_alias).is_connected()
            ):
                raise click.ClickException(
                    "Google authorization did not complete; legacy data was not changed"
                )
            _migrate_legacy_google_index(account_alias)
            click.echo(
                "Removed legacy unscoped Google rows and checkpoints; "
                f"reindexing now targets '{account_alias}'."
            )
        if trigger_sync:
            _sync_sources(ConnectorRegistry, source=source, account=account_alias)
        return

    if trigger_sync:
        _sync_sources(ConnectorRegistry, account=account_alias)
        return

    # No arguments — show help
    click.echo(ctx.get_help())
