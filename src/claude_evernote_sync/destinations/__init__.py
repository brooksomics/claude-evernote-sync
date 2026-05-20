"""Pluggable destinations for syncing a single Claude Code session.

A `Destination` receives one session at a time along with its locked title
and the set of already-synced message UUIDs, and pushes any new content to
Evernote.

- `email`: append-only via Evernote's email-to-note feature (no API key)
- `api`:   full upsert via Evernote NoteStore (currently blocked)
- `mcp`:   future — Evernote's planned MCP integration

Idempotent destinations may ignore `synced_uuids`; the email destination
uses it to send only new messages on subsequent runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from claude_evernote_sync.parser import Message, Session


@dataclass(frozen=True)
class SyncContext:
    session: Session
    bucket: str
    title: str
    synced_uuids: set[str]
    notebook_name: str = "claude_convos"

    @property
    def new_messages(self) -> list[Message]:
        return [m for m in self.session.messages if m.uuid not in self.synced_uuids]

    @property
    def is_first_sync(self) -> bool:
        return not self.synced_uuids


class Destination(Protocol):
    """A sync target. Returns the set of newly-synced message UUIDs."""

    def sync_session(self, ctx: SyncContext) -> set[str]: ...
