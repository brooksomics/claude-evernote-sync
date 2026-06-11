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


def _make_worktree(repo: Path, name: str, gitdir_line: str | None = None) -> Path:
    """Lay out a linked worktree the way `git worktree add` does: the main
    repo gains .git/worktrees/<name>/ and the worktree root gets a .git FILE
    pointing back at it."""
    (repo / ".git" / "worktrees" / name).mkdir(parents=True)
    wt = repo / ".claude" / "worktrees" / name
    wt.mkdir(parents=True)
    line = gitdir_line or f"gitdir: {repo / '.git' / 'worktrees' / name}"
    (wt / ".git").write_text(line + "\n")
    return wt


def test_find_git_root_resolves_linked_worktree_to_main_repo(git_repo: Path) -> None:
    wt = _make_worktree(git_repo, "wt-feature")
    assert find_git_root(wt) == git_repo


def test_bucket_for_worktree_session_is_main_repo_name(git_repo: Path) -> None:
    wt = _make_worktree(git_repo, "w7c-weekly-digest")
    assert bucket_for_cwd(str(wt), overrides=[]) == "myrepo"


def test_worktree_relative_gitdir_resolves_against_worktree(git_repo: Path) -> None:
    rel = "gitdir: ../../../.git/worktrees/wt-rel"
    wt = _make_worktree(git_repo, "wt-rel", gitdir_line=rel)
    assert find_git_root(wt) == git_repo


def test_malformed_git_file_keeps_candidate_dir(tmp_path: Path) -> None:
    odd = tmp_path / "oddball"
    odd.mkdir()
    (odd / ".git").write_text("not a gitdir pointer\n")
    assert find_git_root(odd) == odd


def test_submodule_gitdir_keeps_candidate_dir(tmp_path: Path) -> None:
    """A submodule's .git file points into .git/modules/ — it's its own
    project, so it keeps bucketing under its own directory name."""
    main = tmp_path / "super"
    (main / ".git" / "modules" / "sub").mkdir(parents=True)
    sub = main / "sub"
    sub.mkdir()
    (sub / ".git").write_text(f"gitdir: {main / '.git' / 'modules' / 'sub'}\n")
    assert find_git_root(sub) == sub


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
