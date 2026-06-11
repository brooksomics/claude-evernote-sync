"""Determine the rollup bucket for a session based on its working directory."""

from __future__ import annotations

from pathlib import Path


def find_git_root(start: Path) -> Path | None:
    """Walk up from `start` to the repository root.

    A `.git` directory marks the root directly. A `.git` FILE marks a linked
    worktree (`git worktree add`), which resolves to the main repository so
    worktree sessions bucket with their repo instead of fragmenting into
    one notebook per worktree.
    """
    current = start.resolve()
    for candidate in [current, *current.parents]:
        marker = candidate / ".git"
        if marker.is_dir():
            return candidate
        if marker.is_file():
            return _worktree_main_root(marker) or candidate
    return None


def _worktree_main_root(git_file: Path) -> Path | None:
    """Resolve a linked-worktree `.git` file to the main repository root.

    The file holds `gitdir: <main>/.git/worktrees/<name>` (absolute or
    relative to the worktree root). Anything else — malformed content or a
    submodule's `.git/modules/...` pointer — returns None, since a submodule
    is its own project and should keep its own bucket.
    """
    pointer = git_file.read_text().strip()
    if not pointer.startswith("gitdir:"):
        return None
    gitdir = Path(pointer.removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = (git_file.parent / gitdir).resolve()
    if gitdir.parent.name != "worktrees" or gitdir.parent.parent.name != ".git":
        return None
    return gitdir.parent.parent.parent


def _override_match(cwd: Path, overrides: list[str]) -> str | None:
    for override in overrides:
        override_path = Path(override.rstrip("/")).resolve()
        try:
            cwd.resolve().relative_to(override_path)
        except ValueError:
            continue
        return override_path.name
    return None


def bucket_for_cwd(cwd: str, overrides: list[str]) -> str:
    """Determine the rollup bucket name for a given working directory.

    1. If `cwd` is under any configured override path, use that override's basename.
    2. Else, if a git root is found walking up from `cwd`, use the git root's basename.
    3. Else, use the immediate parent directory's basename.
    """
    cwd_path = Path(cwd)
    override = _override_match(cwd_path, overrides)
    if override:
        return override
    git_root = find_git_root(cwd_path)
    if git_root:
        return git_root.name
    return cwd_path.name or cwd_path.parent.name
