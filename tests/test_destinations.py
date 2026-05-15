"""Tests for destinations: SyncContext, EmailDestination, ApiDestination."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from claude_evernote_sync.credentials import GmailCredentials
from claude_evernote_sync.destinations import SyncContext
from claude_evernote_sync.destinations.api import ApiDestination
from claude_evernote_sync.destinations.email import EmailDestination
from claude_evernote_sync.parser import Message, Session


def _msg(uuid: str, role: str, h: int) -> Message:
    ts = datetime(2026, 5, 15, h, tzinfo=UTC)
    return Message(uuid=uuid, role=role, text=f"text-{uuid}", ts=ts)


def _session(session_id: str, messages: list[Message]) -> Session:
    return Session(
        session_id=session_id,
        cwd="/x/repo",
        git_branch="main",
        version="1.0",
        start_ts=messages[0].ts,
        end_ts=messages[-1].ts,
        messages=messages,
    )


@pytest.fixture
def creds() -> GmailCredentials:
    return GmailCredentials(
        sender="me@gmail.com", app_password="x", evernote_email="me@m.evernote.com"
    )


def test_context_new_messages() -> None:
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = SyncContext("2026-05-15", "x", [s], synced_uuids={"u1"})
    assert [m.uuid for m in ctx.new_messages] == ["u2"]


def test_context_is_first_sync() -> None:
    s = _session("s", [_msg("u1", "user", 10)])
    fresh = SyncContext("2026-05-15", "x", [s], synced_uuids=set())
    seen = SyncContext("2026-05-15", "x", [s], synced_uuids={"u1"})
    assert fresh.is_first_sync
    assert not seen.is_first_sync


def test_context_sessions_with_new() -> None:
    s1 = _session("s1", [_msg("a", "user", 10)])
    s2 = _session("s2", [_msg("b", "user", 11), _msg("c", "assistant", 12)])
    ctx = SyncContext("2026-05-15", "x", [s1, s2], synced_uuids={"a"})
    pairs = ctx.sessions_with_new
    assert pairs[0][1] == []
    assert [m.uuid for m in pairs[1][1]] == ["b", "c"]


def test_email_destination_skips_when_no_new(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10)])
    ctx = SyncContext("2026-05-15", "x", [s], synced_uuids={"u1"})
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        result = dest.sync_group(ctx)
    mock_send.assert_not_called()
    assert result == set()


def test_email_destination_first_sync_creates(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = SyncContext(
        "2026-05-15", "myrepo", [s], synced_uuids=set(), notebook_name="MyBox"
    )
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        result = dest.sync_group(ctx)
    args, _ = mock_send.call_args
    note = args[1]
    assert note.append is False
    assert note.notebook == "MyBox"
    assert "Claude Sessions" in note.title
    assert "myrepo" in note.title
    assert result == {"u1", "u2"}


def test_email_destination_uses_per_bucket_notebook(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10)])
    ctx = SyncContext(
        "2026-05-15", "tile-ai", [s], synced_uuids=set(), notebook_name="TileAI Notes"
    )
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        dest.sync_group(ctx)
    args, _ = mock_send.call_args
    assert args[1].notebook == "TileAI Notes"


def test_email_destination_subsequent_sync_appends(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = SyncContext("2026-05-15", "x", [s], synced_uuids={"u1"})
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        result = dest.sync_group(ctx)
    args, _ = mock_send.call_args
    note = args[1]
    assert note.append is True
    assert result == {"u2"}


def test_api_destination_calls_upsert() -> None:
    client = MagicMock()
    client.get_or_create_notebook.return_value = "nb-guid"
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = SyncContext(
        "2026-05-15", "myrepo", [s], synced_uuids=set(), notebook_name="MyBox"
    )
    dest = ApiDestination(client=client)
    result = dest.sync_group(ctx)
    client.get_or_create_notebook.assert_called_once_with("MyBox")
    client.upsert_note.assert_called_once()
    args, _ = client.upsert_note.call_args
    assert args[0] == "nb-guid"
    assert "myrepo" in args[1]
    assert result == {"u1", "u2"}


def test_api_destination_ignores_synced_state() -> None:
    """API destination is idempotent — re-syncs the full group each time."""
    client = MagicMock()
    client.get_or_create_notebook.return_value = "nb-guid"
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = SyncContext("2026-05-15", "x", [s], synced_uuids={"u1", "u2"})
    dest = ApiDestination(client=client)
    result = dest.sync_group(ctx)
    client.upsert_note.assert_called_once()
    assert result == {"u1", "u2"}


def test_api_destination_caches_notebook_guid() -> None:
    """Repeated syncs for the same notebook only resolve the GUID once."""
    client = MagicMock()
    client.get_or_create_notebook.return_value = "nb-guid"
    s1 = _session("s1", [_msg("u1", "user", 10)])
    s2 = _session("s2", [_msg("u2", "user", 11)])
    ctx1 = SyncContext("2026-05-15", "a", [s1], synced_uuids=set(), notebook_name="MyBox")
    ctx2 = SyncContext("2026-05-15", "b", [s2], synced_uuids=set(), notebook_name="MyBox")
    dest = ApiDestination(client=client)
    dest.sync_group(ctx1)
    dest.sync_group(ctx2)
    assert client.get_or_create_notebook.call_count == 1
