"""Evernote NoteStore API destination (full upsert).

Currently blocked: Evernote suspended new developer-token issuance in Jan 2026.
This destination remains in place for users who already have a token, and as a
ready-to-use path once Evernote reopens API access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from claude_evernote_sync.destinations import SyncContext
from claude_evernote_sync.evernote_client import EvernoteSync
from claude_evernote_sync.formatter import note_title, render_group

logger = logging.getLogger(__name__)


@dataclass
class ApiDestination:
    client: EvernoteSync
    _notebook_cache: dict[str, str] = field(default_factory=dict)

    def sync_group(self, ctx: SyncContext) -> set[str]:
        nb_guid = self._resolve_notebook(ctx.notebook_name)
        title = note_title(ctx.bucket, ctx.date_iso)
        enml = render_group(ctx.date_iso, ctx.bucket, ctx.sessions)
        self.client.upsert_note(nb_guid, title, enml)
        return {m.uuid for m in ctx.all_messages}

    def _resolve_notebook(self, name: str) -> str:
        if name not in self._notebook_cache:
            self._notebook_cache[name] = self.client.get_or_create_notebook(name)
        return self._notebook_cache[name]
