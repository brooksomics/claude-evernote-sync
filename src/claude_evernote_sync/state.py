"""Persistent per-session sync state.

Tracks one SessionRecord per Claude Code session: the set of message UUIDs
already sent to Evernote, plus the title that was locked at first sync
(subsequent appends reuse it so email subject — which is also the matching
key — stays stable).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

STATE_VERSION = 2


@dataclass
class SessionRecord:
    synced_uuids: set[str] = field(default_factory=set)
    title: str = ""


@dataclass
class SyncState:
    sessions: dict[str, SessionRecord] = field(default_factory=dict)

    def record_for(self, session_id: str) -> SessionRecord | None:
        return self.sessions.get(session_id)

    def synced_for(self, session_id: str) -> set[str]:
        record = self.sessions.get(session_id)
        return record.synced_uuids if record else set()

    def is_first_sync(self, session_id: str) -> bool:
        return session_id not in self.sessions

    def mark_synced(self, session_id: str, uuids: Iterable[str], title: str) -> None:
        record = self.sessions.get(session_id)
        if record is None:
            record = SessionRecord(synced_uuids=set(), title=title)
            self.sessions[session_id] = record
        record.synced_uuids.update(uuids)


def load_state(path: Path) -> SyncState:
    if not path.exists():
        return SyncState()
    raw = json.loads(path.read_text())
    if raw.get("version") != STATE_VERSION:
        return SyncState()
    sessions = {
        sid: SessionRecord(synced_uuids=set(rec["synced_uuids"]), title=rec.get("title", ""))
        for sid, rec in raw.get("sessions", {}).items()
    }
    return SyncState(sessions=sessions)


def save_state(state: SyncState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "sessions": {
            sid: {"synced_uuids": sorted(rec.synced_uuids), "title": rec.title}
            for sid, rec in state.sessions.items()
        },
    }
    path.write_text(json.dumps(payload, indent=2))
