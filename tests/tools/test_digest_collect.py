"""Tests for the digest_collect tool."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from openjarvis.connectors._stubs import Document
from openjarvis.core.registry import ConnectorRegistry, ToolRegistry


def test_digest_collect_registered():
    from openjarvis.tools.digest_collect import DigestCollectTool

    ToolRegistry.register_value("digest_collect", DigestCollectTool)
    assert ToolRegistry.contains("digest_collect")


def test_digest_collect_executes():
    from openjarvis.tools.digest_collect import DigestCollectTool

    tool = DigestCollectTool()

    mock_docs = [
        Document(
            doc_id="test-1",
            source="gmail",
            doc_type="email",
            content="Meeting at 3pm",
            title="Team standup",
            author="alice@example.com",
            timestamp=datetime(2026, 4, 1, 10, 0),
        )
    ]

    mock_connector = MagicMock()
    mock_connector.return_value.is_connected.return_value = True
    mock_connector.return_value.sync.return_value = mock_docs

    with patch.object(ConnectorRegistry, "contains", return_value=True):
        with patch.object(ConnectorRegistry, "get", return_value=mock_connector):
            result = tool.execute(sources=["gmail"], hours_back=24)

    assert result.success is True
    assert "=== MESSAGES ===" in result.content
    assert "[gmail id=test-1] From: alice@example.com" in result.content
    assert "Team standup" in result.content
    assert result.metadata["total_items"] == 1


def test_digest_collect_missing_connector():
    from openjarvis.tools.digest_collect import DigestCollectTool

    tool = DigestCollectTool()

    with patch.object(ConnectorRegistry, "contains", return_value=False):
        result = tool.execute(sources=["nonexistent"])

    assert result.success is True  # Partial success
    assert "not available" in result.content


def test_digest_collect_supports_account_scoped_google_source() -> None:
    from openjarvis.tools.digest_collect import DigestCollectTool

    connector_cls = MagicMock()
    connector = connector_cls.return_value
    connector.is_connected.return_value = True
    connector.sync.return_value = [
        Document(
            doc_id="gmail:work:message-1",
            source="gmail",
            doc_type="email",
            content="Work-only update",
            title="Work update",
            author="work@example.com",
            metadata={
                "account": "work",
                "source_profile": "work",
                "message_id": "message-1",
            },
        )
    ]

    with (
        patch.object(ConnectorRegistry, "contains", return_value=True),
        patch.object(ConnectorRegistry, "get", return_value=connector_cls),
        patch("openjarvis.connectors.oauth.get_provider_for_connector") as get_provider,
    ):
        get_provider.return_value.name = "google"
        result = DigestCollectTool().execute(sources=["gmail:Work"])

    connector_cls.assert_called_once_with(account="work")
    assert result.success is True
    assert (
        "[gmail:work id=gmail:work:message-1 account=work message_id=message-1]"
    ) in result.content
