"""Tests for bucket derivation from a session's working directory."""

from pathlib import Path

import pytest

from claude_evernote_sync.grouping import bucket_for_cwd, find_git_root


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
