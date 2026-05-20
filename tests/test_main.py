"""Tests for orchestration + CLI."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from claude_evernote_sync.config import Config
from claude_evernote_sync.destinations import SyncContext
from claude_evernote_sync.main import (
    SyncJob,
    discover_jsonl_files,
    make_destination,
    parse_all,
    run,
)
from claude_evernote_sync.parser import Message, Session
from claude_evernote_sync.state import SyncState


def _write_jsonl(path: Path, ts: str = "2026-05-15T10:00:00.000Z") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "type": "user",
        "uuid": f"u-{path.stem}",
        "timestamp": ts,
        "cwd": "/x/myrepo",
        "sessionId": path.stem,
        "version": "1.0",
        "gitBranch": "main",
        "message": {"role": "user", "content": "hi"},
    }
    path.write_text(json.dumps(line) + "\n")


def _session() -> Session:
    return Session(
        session_id="s1",
        cwd="/x/myrepo",
        git_branch="main",
        version="1.0",
        start_ts=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
        end_ts=datetime(2026, 5, 15, 10, 5, tzinfo=UTC),
        messages=[Message("u1", "user", "hi", datetime(2026, 5, 15, 10, 0, tzinfo=UTC))],
    )


def test_discover_returns_recent_files(tmp_path: Path) -> None:
    recent = tmp_path / "proj-a" / "recent.jsonl"
    _write_jsonl(recent)
    files = discover_jsonl_files(tmp_path, days_back=7)
    assert recent in files


def test_discover_skips_old_files(tmp_path: Path) -> None:
    old = tmp_path / "proj-a" / "old.jsonl"
    _write_jsonl(old)
    old_time = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    os.utime(old, (old_time, old_time))
    files = discover_jsonl_files(tmp_path, days_back=7)
    assert old not in files


def test_discover_missing_dir_returns_empty(tmp_path: Path) -> None:
    files = discover_jsonl_files(tmp_path / "nope", days_back=7)
    assert files == []


def test_parse_all_skips_unparseable(tmp_path: Path) -> None:
    good = tmp_path / "good.jsonl"
    _write_jsonl(good)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    sessions = parse_all([good, empty])
    assert len(sessions) == 1


def test_sync_all_dispatches_to_destination() -> None:
    dest = MagicMock()
    dest.sync_group.return_value = {"u1"}
    state = SyncState()
    config = Config()
    groups = {("2026-05-15", "myrepo"): [_session()]}
    count = SyncJob(destination=dest, state=state, config=config).sync_all(groups)
    assert count == 1
    dest.sync_group.assert_called_once()
    assert state.synced_for(("2026-05-15", "myrepo")) == {"u1"}


def test_sync_all_no_double_count_when_nothing_synced() -> None:
    dest = MagicMock()
    dest.sync_group.return_value = set()
    state = SyncState()
    groups = {("2026-05-15", "x"): [_session()]}
    assert SyncJob(destination=dest, state=state, config=Config()).sync_all(groups) == 0


def test_sync_all_passes_synced_uuids_to_context() -> None:
    dest = MagicMock()
    dest.sync_group.return_value = set()
    state = SyncState()
    state.mark_synced(("2026-05-15", "myrepo"), ["u1"])
    groups = {("2026-05-15", "myrepo"): [_session()]}
    SyncJob(destination=dest, state=state, config=Config()).sync_all(groups)
    ctx_arg: SyncContext = dest.sync_group.call_args.args[0]
    assert ctx_arg.synced_uuids == {"u1"}


def test_sync_all_resolves_notebook_per_bucket() -> None:
    dest = MagicMock()
    dest.sync_group.return_value = set()
    state = SyncState()
    config = Config(notebook_name="default-nb", notebook_overrides={"myrepo": "RepoNotes"})
    groups = {
        ("2026-05-15", "myrepo"): [_session()],
        ("2026-05-15", "other"): [_session()],
    }
    SyncJob(destination=dest, state=state, config=config).sync_all(groups)
    calls = dest.sync_group.call_args_list
    notebooks = {c.args[0].notebook_name for c in calls}
    assert notebooks == {"RepoNotes", "default-nb"}


def test_make_destination_email_backend() -> None:
    config = Config(backend="email")
    with patch("claude_evernote_sync.main.load_credentials") as mock_load:
        mock_load.return_value = MagicMock()
        dest = make_destination(config)
    from claude_evernote_sync.destinations.email import EmailDestination

    assert isinstance(dest, EmailDestination)


def test_make_destination_api_backend() -> None:
    config = Config(backend="api", developer_token="tok")
    with patch("claude_evernote_sync.main.EvernoteSync"):
        dest = make_destination(config)
    from claude_evernote_sync.destinations.api import ApiDestination

    assert isinstance(dest, ApiDestination)


def test_run_dry_run_does_not_create_destination(tmp_path: Path) -> None:
    config = Config(projects_dir=tmp_path, days_back=30)
    _write_jsonl(tmp_path / "encoded" / "session-1.jsonl")
    with patch("claude_evernote_sync.main.make_destination") as mock_make:
        result = run(config, dry_run=True)
    mock_make.assert_not_called()
    assert result == 0


def test_run_calls_destination_when_not_dry(tmp_path: Path) -> None:
    config = Config(backend="email", projects_dir=tmp_path, days_back=30)
    _write_jsonl(tmp_path / "encoded" / "session-1.jsonl")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state") as mock_save_state,
    ):
        dest = MagicMock()
        dest.sync_group.return_value = {"u1"}
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    dest.sync_group.assert_called_once()
    mock_save_state.assert_called_once()


def _captured_session_ids(dest: MagicMock) -> list[str]:
    """Collect every session_id passed in any sync_group call's SyncContext."""
    out: list[str] = []
    for call in dest.sync_group.call_args_list:
        out.extend(s.session_id for s in call.args[0].sessions)
    return out


def test_run_respects_limit(tmp_path: Path) -> None:
    """config.limit=N restricts sync to the N most-recently-active sessions."""
    config = Config(backend="email", projects_dir=tmp_path, days_back=365, limit=2)
    _write_jsonl(tmp_path / "session-old.jsonl", ts="2026-05-01T10:00:00.000Z")
    _write_jsonl(tmp_path / "session-mid.jsonl", ts="2026-05-10T10:00:00.000Z")
    _write_jsonl(tmp_path / "session-new.jsonl", ts="2026-05-20T10:00:00.000Z")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state"),
    ):
        dest = MagicMock()
        dest.sync_group.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    synced = _captured_session_ids(dest)
    assert sorted(synced) == ["session-mid", "session-new"]


def test_run_no_limit_syncs_all(tmp_path: Path) -> None:
    """config.limit=None (the default) leaves all sessions in scope."""
    config = Config(backend="email", projects_dir=tmp_path, days_back=365)
    _write_jsonl(tmp_path / "session-a.jsonl", ts="2026-05-01T10:00:00.000Z")
    _write_jsonl(tmp_path / "session-b.jsonl", ts="2026-05-10T10:00:00.000Z")
    _write_jsonl(tmp_path / "session-c.jsonl", ts="2026-05-20T10:00:00.000Z")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state"),
    ):
        dest = MagicMock()
        dest.sync_group.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    assert sorted(_captured_session_ids(dest)) == ["session-a", "session-b", "session-c"]


def test_run_limit_zero_syncs_nothing(tmp_path: Path) -> None:
    """config.limit=0 means zero sessions sent."""
    config = Config(backend="email", projects_dir=tmp_path, days_back=365, limit=0)
    _write_jsonl(tmp_path / "session-a.jsonl", ts="2026-05-20T10:00:00.000Z")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state"),
    ):
        dest = MagicMock()
        dest.sync_group.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    dest.sync_group.assert_not_called()


def test_run_limit_larger_than_available_is_clamped(tmp_path: Path) -> None:
    """If limit > available sessions, all sessions are kept (no error)."""
    config = Config(backend="email", projects_dir=tmp_path, days_back=365, limit=99)
    _write_jsonl(tmp_path / "session-a.jsonl", ts="2026-05-20T10:00:00.000Z")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state"),
    ):
        dest = MagicMock()
        dest.sync_group.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    assert _captured_session_ids(dest) == ["session-a"]
