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


def _session(session_id: str = "s1", cwd: str = "/x/myrepo") -> Session:
    ts = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)
    return Session(
        session_id=session_id,
        cwd=cwd,
        git_branch="main",
        version="1.0",
        start_ts=ts,
        end_ts=datetime(2026, 5, 15, 10, 5, tzinfo=UTC),
        messages=[Message(f"u-{session_id}", "user", "hi", ts)],
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


def test_sync_all_dispatches_per_session() -> None:
    dest = MagicMock()
    dest.sync_session.return_value = {"u-s1"}
    state = SyncState()
    count = SyncJob(destination=dest, state=state, config=Config()).sync_all([_session()])
    assert count == 1
    dest.sync_session.assert_called_once()
    assert state.synced_for("s1") == {"u-s1"}


def test_sync_all_no_double_count_when_nothing_synced() -> None:
    dest = MagicMock()
    dest.sync_session.return_value = set()
    state = SyncState()
    assert SyncJob(destination=dest, state=state, config=Config()).sync_all([_session()]) == 0


def test_sync_all_passes_locked_title_after_first_sync() -> None:
    """Once a session has a locked title in state, subsequent syncs reuse it."""
    dest = MagicMock()
    dest.sync_session.return_value = set()
    state = SyncState()
    state.mark_synced("s1", ["u-s1"], title="Locked Title - x - s1abcdef")
    SyncJob(destination=dest, state=state, config=Config()).sync_all([_session()])
    ctx_arg: SyncContext = dest.sync_session.call_args.args[0]
    assert ctx_arg.title == "Locked Title - x - s1abcdef"
    assert ctx_arg.synced_uuids == {"u-s1"}


def test_sync_all_derives_title_on_first_sync() -> None:
    """First sync: title is derived from session.summary or first prompt."""
    dest = MagicMock()
    dest.sync_session.return_value = set()
    state = SyncState()
    s = _session()
    s.summary = "Refactor user auth"
    SyncJob(destination=dest, state=state, config=Config()).sync_all([s])
    ctx_arg: SyncContext = dest.sync_session.call_args.args[0]
    assert ctx_arg.title.startswith("Refactor user auth - ")


def test_sync_all_resolves_notebook_per_bucket(tmp_path: Path) -> None:
    repo_a = tmp_path / "repoA"
    repo_b = tmp_path / "repoB"
    (repo_a / ".git").mkdir(parents=True)
    (repo_b / ".git").mkdir(parents=True)
    s_a = _session("sA", cwd=str(repo_a))
    s_b = _session("sB", cwd=str(repo_b))
    dest = MagicMock()
    dest.sync_session.return_value = set()
    config = Config(notebook_name="default-nb", notebook_overrides={"repoA": "RepoNotes"})
    SyncJob(destination=dest, state=SyncState(), config=config).sync_all([s_a, s_b])
    notebooks = {c.args[0].notebook_name for c in dest.sync_session.call_args_list}
    assert notebooks == {"RepoNotes", "default-nb"}


def test_sync_all_applies_notebook_prefix_when_no_override(tmp_path: Path) -> None:
    """With notebook_prefix set, a bucket not listed in notebook_overrides
    routes to `<prefix><bucket>` instead of the catch-all notebook_name."""
    repo = tmp_path / "myproj"
    (repo / ".git").mkdir(parents=True)
    s = _session("s1", cwd=str(repo))
    dest = MagicMock()
    dest.sync_session.return_value = set()
    config = Config(
        notebook_name="convos_default",
        notebook_prefix="convos_",
    )
    SyncJob(destination=dest, state=SyncState(), config=config).sync_all([s])
    ctx_arg = dest.sync_session.call_args.args[0]
    assert ctx_arg.notebook_name == "convos_myproj"


def test_sync_all_override_wins_over_prefix(tmp_path: Path) -> None:
    """An explicit notebook_overrides entry is never re-prefixed; the value
    in the override is used verbatim."""
    repo = tmp_path / "special"
    (repo / ".git").mkdir(parents=True)
    s = _session("s1", cwd=str(repo))
    dest = MagicMock()
    dest.sync_session.return_value = set()
    config = Config(
        notebook_prefix="convos_",
        notebook_overrides={"special": "InboxX"},
    )
    SyncJob(destination=dest, state=SyncState(), config=config).sync_all([s])
    assert dest.sync_session.call_args.args[0].notebook_name == "InboxX"


def test_sync_all_empty_prefix_preserves_legacy_behavior(tmp_path: Path) -> None:
    """Backward-compat: empty notebook_prefix → fall back to notebook_name."""
    repo = tmp_path / "unconfigured"
    (repo / ".git").mkdir(parents=True)
    s = _session("s1", cwd=str(repo))
    dest = MagicMock()
    dest.sync_session.return_value = set()
    config = Config(notebook_name="default-nb", notebook_prefix="")
    SyncJob(destination=dest, state=SyncState(), config=config).sync_all([s])
    assert dest.sync_session.call_args.args[0].notebook_name == "default-nb"


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
        dest.sync_session.return_value = {"u-session-1"}
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    dest.sync_session.assert_called_once()
    mock_save_state.assert_called_once()


def _captured_session_ids(dest: MagicMock) -> list[str]:
    """Collect every session.session_id passed in any sync_session call's SyncContext."""
    return [call.args[0].session.session_id for call in dest.sync_session.call_args_list]


def test_run_respects_limit(tmp_path: Path) -> None:
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
        dest.sync_session.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    assert sorted(_captured_session_ids(dest)) == ["session-mid", "session-new"]


def test_run_no_limit_syncs_all(tmp_path: Path) -> None:
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
        dest.sync_session.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    assert sorted(_captured_session_ids(dest)) == ["session-a", "session-b", "session-c"]


def test_run_limit_zero_syncs_nothing(tmp_path: Path) -> None:
    config = Config(backend="email", projects_dir=tmp_path, days_back=365, limit=0)
    _write_jsonl(tmp_path / "session-a.jsonl", ts="2026-05-20T10:00:00.000Z")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state"),
    ):
        dest = MagicMock()
        dest.sync_session.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    dest.sync_session.assert_not_called()


def test_run_limit_larger_than_available_is_clamped(tmp_path: Path) -> None:
    config = Config(backend="email", projects_dir=tmp_path, days_back=365, limit=99)
    _write_jsonl(tmp_path / "session-a.jsonl", ts="2026-05-20T10:00:00.000Z")
    with (
        patch("claude_evernote_sync.main.make_destination") as mock_make,
        patch("claude_evernote_sync.main.load_state") as mock_load_state,
        patch("claude_evernote_sync.main.save_state"),
    ):
        dest = MagicMock()
        dest.sync_session.return_value = set()
        mock_make.return_value = dest
        mock_load_state.return_value = SyncState()
        run(config, dry_run=False)
    assert _captured_session_ids(dest) == ["session-a"]


def test_sync_all_force_resends_already_synced_session() -> None:
    """force=True clears the per-session record before each sync, so the
    destination sees the session as a fresh first-sync and re-sends every
    message. Combined with --limit, this lets users re-render a small
    sample after deleting the existing notes in Evernote."""
    dest = MagicMock()
    dest.sync_session.return_value = {"u-s1"}
    state = SyncState()
    state.mark_synced("s1", ["u-s1"], title="Stale Title - x - s1abcd")
    config = Config(force=True)
    SyncJob(destination=dest, state=state, config=config).sync_all([_session()])
    ctx_arg: SyncContext = dest.sync_session.call_args.args[0]
    assert ctx_arg.synced_uuids == set()
    assert ctx_arg.is_first_sync


def test_sync_all_force_redrives_title_from_session() -> None:
    """force=True ignores the stale locked title and re-derives from the
    current Session (its summary / first-prompt / fallback)."""
    dest = MagicMock()
    dest.sync_session.return_value = set()
    state = SyncState()
    state.mark_synced("s1", ["u-s1"], title="Stale Title - x - s1abcd")
    s = _session()
    s.summary = "Refreshed Topic"
    SyncJob(destination=dest, state=state, config=Config(force=True)).sync_all([s])
    ctx_arg: SyncContext = dest.sync_session.call_args.args[0]
    assert ctx_arg.title.startswith("Refreshed Topic - ")


def test_sync_all_without_force_keeps_locked_title() -> None:
    """Confirms the non-force path is unchanged after the force feature lands."""
    dest = MagicMock()
    dest.sync_session.return_value = set()
    state = SyncState()
    state.mark_synced("s1", ["u-s1"], title="Locked Title - x - s1abcdef")
    s = _session()
    s.summary = "DIFFERENT"
    SyncJob(destination=dest, state=state, config=Config(force=False)).sync_all([s])
    ctx_arg: SyncContext = dest.sync_session.call_args.args[0]
    assert ctx_arg.title == "Locked Title - x - s1abcdef"
