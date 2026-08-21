"""Named-account boundaries for proactive Google actions."""

from unittest.mock import patch

from openjarvis.tools.proactive_tools import (
    _exec_calendar_accept,
    _exec_email_archive,
    _exec_email_delete,
)


def test_email_action_uses_named_connector_and_native_id() -> None:
    with patch("openjarvis.connectors.gmail.GmailConnector") as connector_cls:
        ok, _ = _exec_email_delete(
            {"account": "Work", "message_id": "gmail:work:message-42"}
        )

    assert ok is True
    connector_cls.assert_called_once_with(account="work")
    connector_cls.return_value.delete_message.assert_called_once_with("message-42")


def test_legacy_prefixed_email_action_recovers_account() -> None:
    with patch("openjarvis.connectors.gmail.GmailConnector") as connector_cls:
        ok, _ = _exec_email_archive({"message_id": "gmail:personal:message-7"})

    assert ok is True
    connector_cls.assert_called_once_with(account="personal")
    connector_cls.return_value.archive_message.assert_called_once_with("message-7")


def test_calendar_action_uses_named_connector_and_native_id() -> None:
    with patch("openjarvis.connectors.gcalendar.GCalendarConnector") as connector_cls:
        ok, _ = _exec_calendar_accept(
            {
                "account": "Family",
                "event_id": "gcalendar:family:event-9",
                "calendar_id": "primary",
            }
        )

    assert ok is True
    connector_cls.assert_called_once_with(account="family")
    connector_cls.return_value.accept_event.assert_called_once_with(
        "event-9", calendar_id="primary"
    )


def test_disabled_profile_cannot_execute_proactive_google_action() -> None:
    from openjarvis.core.config import GoogleAccountProfileConfig, JarvisConfig

    config = JarvisConfig()
    config.connectors.google.accounts["work"] = GoogleAccountProfileConfig(
        enabled=False
    )

    with (
        patch("openjarvis.core.config.load_config", return_value=config),
        patch("openjarvis.connectors.gmail.GmailConnector") as connector_cls,
    ):
        ok, message = _exec_email_delete(
            {"account": "work", "message_id": "message-42"}
        )

    assert ok is False
    assert "disabled" in message
    connector_cls.assert_not_called()
