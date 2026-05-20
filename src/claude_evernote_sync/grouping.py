"""Determine the rollup bucket for a session based on its working directory."""

from __future__ import annotations

from pathlib import Path


def find_git_root(start: Path) -> Path | None:
    """Walk up from `start` looking for a `.git` directory."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


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
