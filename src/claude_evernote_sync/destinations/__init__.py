"""Pluggable destinations for syncing Claude Code sessions.

A `Destination` is something that can receive a group of sessions for a given
(date, bucket) and persist them. Different destinations have different
constraints:

- `email`: append-only via Evernote's email-to-note feature (no API key required)
- `api`:   full upsert via Evernote NoteStore (currently blocked; ready when API reopens)
- `mcp`:   future — Evernote's planned MCP integration

Destinations may use the per-group sync state (set of already-synced message
UUIDs) to send only new content. Idempotent destinations may ignore it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from claude_evernote_sync.parser import Message, Session


@dataclass(frozen=True)
class SyncContext:
    date_iso: str
    bucket: str
    sessions: list[Session]
    synced_uuids: set[str]
    notebook_name: str = "claude_convos"

    @property
    def all_messages(self) -> list[Message]:
        return [m for s in self.sessions for m in s.messages]

    @property
    def new_messages(self) -> list[Message]:
        return [m for m in self.all_messages if m.uuid not in self.synced_uuids]

    @property
    def is_first_sync(self) -> bool:
        return not self.synced_uuids

    @property
    def sessions_with_new(self) -> list[tuple[Session, list[Message]]]:
        return [
            (s, [m for m in s.messages if m.uuid not in self.synced_uuids]) for s in self.sessions
        ]


class Destination(Protocol):
    """A sync target. Returns the set of newly-synced message UUIDs."""

    def sync_group(self, ctx: SyncContext) -> set[str]: ...
