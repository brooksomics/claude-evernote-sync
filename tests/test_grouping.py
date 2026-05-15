"""Tests for session grouping by date and parent directory."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_evernote_sync.grouping import (
    bucket_for_cwd,
    find_git_root,
    group_sessions,
)
from claude_evernote_sync.parser import Message, Session


def _make_session(session_id: str, cwd: str, ts: datetime) -> Session:
    msg = Message(uuid=f"{session_id}-u1", role="user", text="hi", ts=ts)
    return Session(
        session_id=session_id,
        cwd=cwd,
        git_branch="main",
        version="1.0",
        start_ts=ts,
        end_ts=ts,
        messages=[msg],
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "myrepo"
    (repo / "subdir").mkdir(parents=True)
    (repo / ".git").mkdir()
    return repo


def test_find_git_root_at_repo(git_repo: Path) -> None:
    assert find_git_root(git_repo) == git_repo


def test_find_git_root_from_subdir(git_repo: Path) -> None:
    assert find_git_root(git_repo / "subdir") == git_repo


def test_find_git_root_not_found(tmp_path: Path) -> None:
    no_repo = tmp_path / "no-git"
    no_repo.mkdir()
    assert find_git_root(no_repo) is None


def test_bucket_uses_git_root_basename(git_repo: Path) -> None:
    bucket = bucket_for_cwd(str(git_repo / "subdir"), overrides=[])
    assert bucket == "myrepo"


def test_bucket_falls_back_to_cwd_basename_when_no_git(tmp_path: Path) -> None:
    plain = tmp_path / "container" / "leaf"
    plain.mkdir(parents=True)
    bucket = bucket_for_cwd(str(plain), overrides=[])
    assert bucket == "leaf"


def test_bucket_uses_override_when_path_under_it(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    repo1 = workspace / "repo1"
    (repo1 / ".git").mkdir(parents=True)
    bucket = bucket_for_cwd(str(repo1), overrides=[str(workspace)])
    assert bucket == "workspace"


def test_override_with_trailing_slash_matches(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    repo1 = workspace / "r1"
    (repo1 / ".git").mkdir(parents=True)
    bucket = bucket_for_cwd(str(repo1), overrides=[str(workspace) + "/"])
    assert bucket == "ws"


def test_override_not_used_when_path_not_under_it(tmp_path: Path) -> None:
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bucket = bucket_for_cwd(str(other), overrides=[str(workspace)])
    assert bucket == "other"


def test_group_by_date_and_bucket() -> None:
    s1 = _make_session("s1", "/x/repoA", datetime(2026, 5, 15, 10, 0, tzinfo=UTC))
    s2 = _make_session("s2", "/x/repoA", datetime(2026, 5, 15, 14, 0, tzinfo=UTC))
    s3 = _make_session("s3", "/x/repoB", datetime(2026, 5, 15, 9, 0, tzinfo=UTC))
    s4 = _make_session("s4", "/x/repoA", datetime(2026, 5, 16, 9, 0, tzinfo=UTC))
    groups = group_sessions([s1, s2, s3, s4], overrides=[])
    assert len(groups) == 3
    assert ("2026-05-15", "repoA") in groups
    assert ("2026-05-15", "repoB") in groups
    assert ("2026-05-16", "repoA") in groups
    assert len(groups[("2026-05-15", "repoA")]) == 2


def test_group_sorts_sessions_within_bucket_by_start_ts() -> None:
    s_late = _make_session("late", "/x/r", datetime(2026, 5, 15, 14, 0, tzinfo=UTC))
    s_early = _make_session("early", "/x/r", datetime(2026, 5, 15, 9, 0, tzinfo=UTC))
    groups = group_sessions([s_late, s_early], overrides=[])
    bucket_key = next(iter(groups))
    assert [s.session_id for s in groups[bucket_key]] == ["early", "late"]


def test_group_uses_local_date_from_session_start(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 15, 23, 30, tzinfo=UTC)
    s = _make_session("s", str(tmp_path), ts)
    groups = group_sessions([s], overrides=[])
    date_keys = {k[0] for k in groups}
    assert "2026-05-15" in date_keys
