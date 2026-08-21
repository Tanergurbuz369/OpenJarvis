"""Account-scoped ``jarvis ask`` CLI regressions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from openjarvis.cli.ask import _normalise_account_filters, ask
from openjarvis.core.config import JarvisConfig


def test_normalise_account_filters_deduplicates_aliases() -> None:
    assert _normalise_account_filters((" Work ", "personal"), "work,research") == [
        "work",
        "personal",
        "research",
    ]


def test_account_filters_imply_research_and_reach_agent() -> None:
    config = JarvisConfig()
    with (
        patch("openjarvis.cli.ask.print_banner"),
        patch("openjarvis.cli.ask.load_config", return_value=config),
        patch("openjarvis.cli.ask.register_builtin_models"),
        patch(
            "openjarvis.cli.ask.get_engine",
            return_value=("fake", MagicMock()),
        ),
        patch("openjarvis.cli.ask._run_research") as run_research,
    ):
        result = CliRunner().invoke(
            ask,
            ["--account", "Work", "--accounts", "personal,work", "updates"],
        )

    assert result.exit_code == 0, result.output
    assert run_research.call_args.kwargs["accounts"] == ["work", "personal"]


def test_invalid_account_filter_fails_before_engine_discovery() -> None:
    with patch("openjarvis.cli.ask.load_config", return_value=JarvisConfig()):
        result = CliRunner().invoke(ask, ["--account", "../work", "updates"])

    assert result.exit_code == 2
    assert "Account aliases must" in result.output
