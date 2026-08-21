"""Tests for MorningDigestAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from openjarvis.agents._stubs import AgentResult
from openjarvis.core.registry import AgentRegistry
from openjarvis.core.types import ToolResult


def test_morning_digest_registered():
    from openjarvis.agents.morning_digest import MorningDigestAgent

    AgentRegistry.register_value("morning_digest", MorningDigestAgent)
    assert AgentRegistry.contains("morning_digest")


def test_expand_account_sources_scopes_only_google_connectors() -> None:
    from openjarvis.agents.morning_digest import expand_account_sources

    assert expand_account_sources(
        ["gmail", "gcalendar:family", "slack"],
        [" Work ", "personal"],
    ) == [
        "gmail:work",
        "gmail:personal",
        "gcalendar:family",
        "slack",
    ]


def test_expand_account_sources_fails_closed_when_profiles_are_disabled() -> None:
    from openjarvis.agents.morning_digest import expand_account_sources

    assert expand_account_sources(
        ["gmail", "gcalendar:disabled", "slack"],
        [],
        is_account_enabled=lambda account: account != "disabled",
    ) == ["slack"]


def test_expand_account_sources_keeps_unconfigured_legacy_google_source() -> None:
    from openjarvis.agents.morning_digest import expand_account_sources

    assert expand_account_sources(["gmail", "slack"], None) == ["gmail", "slack"]


def test_morning_digest_run(tmp_path):
    from openjarvis.agents.morning_digest import MorningDigestAgent

    mock_engine = MagicMock()
    mock_engine.generate.return_value = {
        "content": "Good morning sir. AtlasDB 1.0 was released.",
        "finish_reason": "stop",
        "usage": {},
    }

    # Mock collect result
    mock_collect_result = ToolResult(
        tool_name="digest_collect",
        content="=== WORLD ===\n[hackernews] AtlasDB 1.0 Released — 241 points\n",
        success=True,
        metadata={"total_items": 2},
    )

    # Mock TTS result
    mock_tts_result = ToolResult(
        tool_name="text_to_speech",
        content=str(tmp_path / "digest.mp3"),
        success=True,
        metadata={"audio_path": str(tmp_path / "digest.mp3")},
    )

    agent = MorningDigestAgent(
        mock_engine,
        "test-model",
        tools=[],
        persona="jarvis",
        sections=["world"],
        section_sources={"world": ["hackernews", "news_rss"]},
        digest_store_path=str(tmp_path / "digest.db"),
    )

    with patch.object(
        agent._executor,
        "execute",
        side_effect=[mock_collect_result, mock_tts_result],
    ):
        result = agent.run("Generate morning digest")

    assert isinstance(result, AgentResult)
    assert "Good morning" in result.content
    assert result.turns == 1
    assert len(result.tool_results) == 2
    assert set(result.metadata["sources_used"]) == {"hackernews", "news_rss"}
    prompt = "\n".join(
        message.text for message in mock_engine.generate.call_args.args[0]
    ).casefold()
    assert "world —" in prompt
    for forbidden in (
        "messages —|calendar —|health —|rebuttal|dinner at|group chat|"
        "slack|next meeting|readiness|hrv|weather"
    ).split("|"):
        assert forbidden not in prompt


def test_load_persona():
    from openjarvis.agents.morning_digest import _load_persona

    # Nonexistent persona returns empty string
    result = _load_persona("nonexistent_persona_xyz")
    assert result == ""
