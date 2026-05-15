"""Persistent sync state — which message UUIDs have been pushed per group."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from claude_evernote_sync.grouping import GroupKey

STATE_VERSION = 1


@dataclass
class SyncState:
    groups: dict[str, set[str]] = field(default_factory=dict)

    def synced_for(self, key: GroupKey) -> set[str]:
        return self.groups.get(_str_key(key), set())

    def mark_synced(self, key: GroupKey, uuids: Iterable[str]) -> None:
        bucket = self.groups.setdefault(_str_key(key), set())
        bucket.update(uuids)

    def is_first_sync(self, key: GroupKey) -> bool:
        return _str_key(key) not in self.groups


def _str_key(key: GroupKey) -> str:
    return f"{key[0]}|{key[1]}"


def load_state(path: Path) -> SyncState:
    if not path.exists():
        return SyncState()
    raw = json.loads(path.read_text())
    groups = {k: set(v) for k, v in raw.get("groups", {}).items()}
    return SyncState(groups=groups)


def save_state(state: SyncState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "groups": {k: sorted(v) for k, v in state.groups.items()},
    }
    path.write_text(json.dumps(payload, indent=2))
