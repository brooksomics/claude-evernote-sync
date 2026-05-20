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


def _ctx(session: Session, **kwargs: object) -> SyncContext:
    defaults: dict[str, object] = {
        "bucket": "myrepo",
        "title": "Topic - myrepo - abc12345",
        "synced_uuids": set(),
        "notebook_name": "MyBox",
    }
    defaults.update(kwargs)
    return SyncContext(session=session, **defaults)  # type: ignore[arg-type]


@pytest.fixture
def creds() -> GmailCredentials:
    return GmailCredentials(
        sender="me@gmail.com", app_password="x", evernote_email="me@m.evernote.com"
    )


def test_context_new_messages() -> None:
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = _ctx(s, synced_uuids={"u1"})
    assert [m.uuid for m in ctx.new_messages] == ["u2"]


def test_context_is_first_sync() -> None:
    s = _session("s", [_msg("u1", "user", 10)])
    fresh = _ctx(s, synced_uuids=set())
    seen = _ctx(s, synced_uuids={"u1"})
    assert fresh.is_first_sync
    assert not seen.is_first_sync


def test_email_destination_skips_when_no_new(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10)])
    ctx = _ctx(s, synced_uuids={"u1"})
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        result = dest.sync_session(ctx)
    mock_send.assert_not_called()
    assert result == set()


def test_email_destination_first_sync_creates(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = _ctx(s, title="My Topic - myrepo - sabc1234")
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        result = dest.sync_session(ctx)
    args, _ = mock_send.call_args
    note = args[1]
    assert note.append is False
    assert note.notebook == "MyBox"
    assert note.title == "My Topic - myrepo - sabc1234"
    assert result == {"u1", "u2"}


def test_email_destination_uses_notebook_name(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10)])
    ctx = _ctx(s, notebook_name="TileAI Notes")
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        dest.sync_session(ctx)
    args, _ = mock_send.call_args
    assert args[1].notebook == "TileAI Notes"


def test_email_destination_subsequent_sync_appends(creds: GmailCredentials) -> None:
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = _ctx(s, synced_uuids={"u1"})
    dest = EmailDestination(creds=creds)
    with patch("claude_evernote_sync.destinations.email.send") as mock_send:
        result = dest.sync_session(ctx)
    args, _ = mock_send.call_args
    note = args[1]
    assert note.append is True
    assert result == {"u2"}


def test_api_destination_calls_upsert() -> None:
    client = MagicMock()
    client.get_or_create_notebook.return_value = "nb-guid"
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = _ctx(s, title="Locked Title - myrepo - sabc1234")
    dest = ApiDestination(client=client)
    result = dest.sync_session(ctx)
    client.get_or_create_notebook.assert_called_once_with("MyBox")
    client.upsert_note.assert_called_once()
    args, _ = client.upsert_note.call_args
    assert args[0] == "nb-guid"
    assert args[1] == "Locked Title - myrepo - sabc1234"
    assert result == {"u1", "u2"}


def test_api_destination_ignores_synced_state() -> None:
    """API destination is idempotent — re-syncs the full session each time."""
    client = MagicMock()
    client.get_or_create_notebook.return_value = "nb-guid"
    s = _session("s", [_msg("u1", "user", 10), _msg("u2", "assistant", 11)])
    ctx = _ctx(s, synced_uuids={"u1", "u2"})
    dest = ApiDestination(client=client)
    result = dest.sync_session(ctx)
    client.upsert_note.assert_called_once()
    assert result == {"u1", "u2"}


def test_api_destination_caches_notebook_guid() -> None:
    """Repeated syncs for the same notebook only resolve the GUID once."""
    client = MagicMock()
    client.get_or_create_notebook.return_value = "nb-guid"
    s1 = _session("s1", [_msg("u1", "user", 10)])
    s2 = _session("s2", [_msg("u2", "user", 11)])
    ctx1 = _ctx(s1)
    ctx2 = _ctx(s2)
    dest = ApiDestination(client=client)
    dest.sync_session(ctx1)
    dest.sync_session(ctx2)
    assert client.get_or_create_notebook.call_count == 1
