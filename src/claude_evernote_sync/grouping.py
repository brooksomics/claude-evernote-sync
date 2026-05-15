"""Bucket sessions by parent directory and group by date."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from claude_evernote_sync.parser import Session

GroupKey = tuple[str, str]  # (date_iso, bucket_name)


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


def group_sessions(sessions: list[Session], overrides: list[str]) -> dict[GroupKey, list[Session]]:
    """Group sessions by (start-date, bucket-name); sort each bucket by start_ts."""
    groups: dict[GroupKey, list[Session]] = defaultdict(list)
    for session in sessions:
        date_str = session.start_ts.date().isoformat()
        bucket = bucket_for_cwd(session.cwd, overrides)
        groups[(date_str, bucket)].append(session)
    for sessions_in_group in groups.values():
        sessions_in_group.sort(key=lambda s: s.start_ts)
    return dict(groups)
