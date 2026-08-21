"""Tests for ``jarvis connect`` CLI command."""

from __future__ import annotations

from unittest import mock

from click.testing import CliRunner

from openjarvis.cli import cli


def test_connect_list_no_connectors() -> None:
    """--list with an empty registry shows a 'no connectors' message."""
    runner = CliRunner()
    with mock.patch(
        "openjarvis.cli.connect_cmd.connect.__wrapped__"
        if hasattr(cli, "__wrapped__")
        else "openjarvis.core.registry.ConnectorRegistry.items",
        return_value=(),
    ):
        with mock.patch(
            "openjarvis.core.registry.ConnectorRegistry.items",
            return_value=(),
        ):
            result = runner.invoke(cli, ["connect", "--list"])

    assert result.exit_code == 0
    assert "No connectors registered" in result.output


def test_connect_list_with_connector(tmp_path: object) -> None:
    """--list with a connector registered shows it in the table."""
    runner = CliRunner()

    # Build a minimal mock connector class
    mock_cls = mock.MagicMock()
    mock_cls.auth_type = "filesystem"
    mock_instance = mock.MagicMock()
    mock_instance.is_connected.return_value = True
    mock_cls.return_value = mock_instance

    with mock.patch(
        "openjarvis.core.registry.ConnectorRegistry.items",
        return_value=(("obsidian", mock_cls),),
    ):
        result = runner.invoke(cli, ["connect", "--list"])

    assert result.exit_code == 0
    assert "obsidian" in result.output


def test_connect_help() -> None:
    """--help exits 0 and mentions the word 'connect'."""
    runner = CliRunner()
    result = runner.invoke(cli, ["connect", "--help"])
    assert result.exit_code == 0
    assert "connect" in result.output.lower()


def test_connect_specific_source(tmp_path: object) -> None:
    """connect --path /nonexistent obsidian shows an error gracefully."""
    runner = CliRunner()

    mock_cls = mock.MagicMock()
    mock_cls.auth_type = "filesystem"
    mock_instance = mock.MagicMock()
    # Path does not exist -> is_connected returns False
    mock_instance.is_connected.return_value = False
    mock_cls.return_value = mock_instance

    with (
        mock.patch(
            "openjarvis.core.registry.ConnectorRegistry.contains",
            return_value=True,
        ),
        mock.patch(
            "openjarvis.core.registry.ConnectorRegistry.get",
            return_value=mock_cls,
        ),
    ):
        # --path before the positional source arg (standard Click group behaviour)
        result = runner.invoke(cli, ["connect", "--path", "/nonexistent", "obsidian"])

    assert result.exit_code == 0
    # Should mention the source and give an indication something went wrong
    assert "obsidian" in result.output or "nonexistent" in result.output


def test_connect_disconnect() -> None:
    """--disconnect gmail exits 0."""
    runner = CliRunner()

    mock_cls = mock.MagicMock()
    mock_instance = mock.MagicMock()
    mock_cls.return_value = mock_instance

    with (
        mock.patch(
            "openjarvis.core.registry.ConnectorRegistry.contains",
            return_value=True,
        ),
        mock.patch(
            "openjarvis.core.registry.ConnectorRegistry.get",
            return_value=mock_cls,
        ),
    ):
        result = runner.invoke(cli, ["connect", "--disconnect", "gmail"])

    assert result.exit_code == 0
    mock_instance.disconnect.assert_called_once()


def test_connect_google_with_account_runs_segmented_oauth() -> None:
    """connect google --account work routes OAuth through the account alias."""
    runner = CliRunner()

    with (
        mock.patch(
            "openjarvis.connectors.oauth.get_client_credentials",
            return_value=("client.apps.googleusercontent.com", "secret"),
        ),
        mock.patch("openjarvis.connectors.oauth.run_connector_oauth") as mock_run,
    ):
        result = runner.invoke(cli, ["connect", "--account", "work", "google"])

    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "gmail",
        "client.apps.googleusercontent.com",
        "secret",
        account="work",
    )


def test_connect_rejects_conflicting_account_and_profile_aliases() -> None:
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["connect", "--account", "work", "--profile", "personal", "google"],
    )

    assert result.exit_code == 2
    assert "must name the same alias" in result.output


def test_connect_accepts_equivalent_canonical_account_and_profile() -> None:
    runner = CliRunner()

    with (
        mock.patch(
            "openjarvis.connectors.oauth.get_client_credentials",
            return_value=("client.apps.googleusercontent.com", "secret"),
        ),
        mock.patch("openjarvis.connectors.oauth.run_connector_oauth") as mock_run,
    ):
        result = runner.invoke(
            cli,
            ["connect", "--account", " Work ", "--profile", "work", "google"],
        )

    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "gmail",
        "client.apps.googleusercontent.com",
        "secret",
        account="work",
    )


def test_disconnect_named_google_account_purges_index_before_token() -> None:
    runner = CliRunner()

    with (
        mock.patch("openjarvis.cli.connect_cmd._purge_google_account_index") as purge,
        mock.patch("openjarvis.connectors.oauth.delete_tokens") as delete,
        mock.patch(
            "openjarvis.connectors.oauth.google_account_credentials_path",
            return_value="/tmp/work.json",
        ),
    ):
        result = runner.invoke(
            cli,
            ["connect", "--account", "work", "--disconnect", "gmail"],
        )

    assert result.exit_code == 0
    purge.assert_called_once_with("work")
    delete.assert_called_once_with("/tmp/work.json")


def test_connect_rejects_named_account_for_non_google_source() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["connect", "--account", "work", "obsidian"])

    assert result.exit_code == 2
    assert "supported only for Google connectors" in result.output


def test_connect_rejects_unsafe_account_alias() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["connect", "--account", "../work", "google"])

    assert result.exit_code == 2
    assert "Account aliases must be" in result.output


def test_connect_google_account_can_sync_after_oauth() -> None:
    runner = CliRunner()

    with (
        mock.patch("openjarvis.cli.connect_cmd._connect_source") as connect_source,
        mock.patch("openjarvis.cli.connect_cmd._sync_sources") as sync_sources,
    ):
        result = runner.invoke(
            cli,
            ["connect", "--account", "work", "--sync", "google"],
        )

    assert result.exit_code == 0
    connect_source.assert_called_once()
    sync_sources.assert_called_once()
    assert sync_sources.call_args.kwargs == {"source": "google", "account": "work"}


def test_legacy_migration_is_explicit_and_precedes_named_sync() -> None:
    runner = CliRunner()
    calls: list[str] = []

    with (
        mock.patch(
            "openjarvis.cli.connect_cmd._migrate_legacy_google_index",
            side_effect=lambda account: calls.append(f"migrate:{account}"),
        ),
        mock.patch(
            "openjarvis.cli.connect_cmd._connect_source",
            side_effect=lambda *args, **kwargs: calls.append("connect") or True,
        ),
        mock.patch(
            "openjarvis.cli.connect_cmd._sync_sources",
            side_effect=lambda *args, **kwargs: calls.append("sync"),
        ),
        mock.patch(
            "openjarvis.connectors.gmail.GmailConnector.is_connected",
            return_value=True,
        ),
    ):
        result = runner.invoke(
            cli,
            [
                "connect",
                "--account",
                "work",
                "--migrate-legacy-google",
                "--sync",
                "google",
            ],
        )

    assert result.exit_code == 0
    assert calls == ["connect", "migrate:work", "sync"]


def test_failed_google_oauth_does_not_migrate_existing_legacy_rows() -> None:
    runner = CliRunner()

    with (
        mock.patch(
            "openjarvis.connectors.gmail.GmailConnector.is_connected",
            return_value=False,
        ),
        mock.patch(
            "openjarvis.connectors.oauth.get_client_credentials",
            return_value=("client.apps.googleusercontent.com", "secret"),
        ),
        mock.patch(
            "openjarvis.connectors.oauth.run_connector_oauth",
            side_effect=RuntimeError("provider rejected reauth"),
        ),
        mock.patch(
            "openjarvis.cli.connect_cmd._migrate_legacy_google_index"
        ) as migrate,
    ):
        result = runner.invoke(
            cli,
            ["connect", "--account", "work", "--migrate-legacy-google", "google"],
        )

    assert result.exit_code == 1
    assert "legacy data was not changed" in result.output
    migrate.assert_not_called()


def test_copied_named_token_can_migrate_without_reauthentication() -> None:
    runner = CliRunner()

    with (
        mock.patch(
            "openjarvis.connectors.gmail.GmailConnector.is_connected",
            return_value=True,
        ),
        mock.patch("openjarvis.connectors.oauth.run_connector_oauth") as oauth,
        mock.patch(
            "openjarvis.cli.connect_cmd._migrate_legacy_google_index"
        ) as migrate,
    ):
        result = runner.invoke(
            cli,
            ["connect", "--account", "work", "--migrate-legacy-google", "google"],
        )

    assert result.exit_code == 0, result.output
    oauth.assert_not_called()
    migrate.assert_called_once_with("work")


def test_legacy_migration_preserves_ambiguous_gmail_rows() -> None:
    from openjarvis.cli.connect_cmd import _migrate_legacy_google_index

    store = mock.MagicMock()
    store.__enter__.return_value = store
    engine = mock.MagicMock()
    engine.__enter__.return_value = engine

    with (
        mock.patch(
            "openjarvis.connectors.store.KnowledgeStore",
            return_value=store,
        ),
        mock.patch(
            "openjarvis.connectors.sync_engine.SyncEngine",
            return_value=engine,
        ),
    ):
        _migrate_legacy_google_index("work")

    calls = store.delete_by_sources.call_args_list
    assert calls[-2].kwargs == {"unscoped_only": True}
    assert "gmail" not in calls[-2].args[0]
    assert calls[-1].args == (("gmail",),)
    assert calls[-1].kwargs == {
        "unscoped_only": True,
        "metadata_connector": "gmail",
    }


def test_disabled_configured_google_account_is_rejected(monkeypatch) -> None:
    from openjarvis.core.config import (
        GoogleAccountProfileConfig,
        JarvisConfig,
    )

    config = JarvisConfig()
    config.connectors.google.accounts["work"] = GoogleAccountProfileConfig(
        enabled=False
    )
    monkeypatch.setattr("openjarvis.core.config.load_config", lambda: config)

    result = CliRunner().invoke(cli, ["connect", "--account", "work", "google"])

    assert result.exit_code == 2
    assert "disabled in config.toml" in result.output


def test_disabled_google_account_can_still_be_disconnected(monkeypatch) -> None:
    from openjarvis.core.config import GoogleAccountProfileConfig, JarvisConfig

    config = JarvisConfig()
    config.connectors.google.accounts["work"] = GoogleAccountProfileConfig(
        enabled=False
    )
    monkeypatch.setattr("openjarvis.core.config.load_config", lambda: config)

    with mock.patch("openjarvis.cli.connect_cmd._purge_google_account_index") as purge:
        result = CliRunner().invoke(
            cli,
            ["connect", "--account", "work", "--disconnect", "google"],
        )

    assert result.exit_code == 0, result.output
    purge.assert_called_once_with("work")
