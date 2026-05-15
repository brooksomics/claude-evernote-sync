"""Tests for the SMTP email client."""

from unittest.mock import MagicMock, patch

import pytest

from claude_evernote_sync.credentials import GmailCredentials
from claude_evernote_sync.email_client import EmailNote, build_subject, send


@pytest.fixture
def creds() -> GmailCredentials:
    return GmailCredentials(
        sender="me@gmail.com",
        app_password="secret",
        evernote_email="me.xxx@m.evernote.com",
    )


def test_build_subject_plain() -> None:
    note = EmailNote(title="Hello", html_body="")
    assert build_subject(note) == "Hello"


def test_build_subject_with_notebook() -> None:
    note = EmailNote(title="Hello", html_body="", notebook="Claude Sessions")
    assert build_subject(note) == "Hello @Claude Sessions"


def test_build_subject_with_append() -> None:
    note = EmailNote(title="Hello", html_body="", append=True)
    assert build_subject(note) == "Hello +"


def test_build_subject_notebook_then_append() -> None:
    note = EmailNote(title="Hello", html_body="", notebook="Box", append=True)
    assert build_subject(note) == "Hello @Box +"


def test_send_logs_in_with_creds(creds: GmailCredentials) -> None:
    note = EmailNote(title="T", html_body="<p>hi</p>")
    with patch("claude_evernote_sync.email_client.smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        send(creds, note)
    mock_server.login.assert_called_once_with("me@gmail.com", "secret")


def test_send_addresses_evernote_email(creds: GmailCredentials) -> None:
    note = EmailNote(title="T", html_body="<p>hi</p>")
    with patch("claude_evernote_sync.email_client.smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        send(creds, note)
    args, _ = mock_server.sendmail.call_args
    assert args[0] == "me@gmail.com"
    assert args[1] == "me.xxx@m.evernote.com"


def test_send_includes_subject_and_html(creds: GmailCredentials) -> None:
    note = EmailNote(title="MyNote", html_body="<h1>Test</h1>", notebook="Box")
    with patch("claude_evernote_sync.email_client.smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        send(creds, note)
    args, _ = mock_server.sendmail.call_args
    raw_message = args[2]
    assert "Subject: MyNote @Box" in raw_message
    assert "<h1>Test</h1>" in raw_message
