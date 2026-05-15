"""Email-to-Evernote destination (append-only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from claude_evernote_sync.credentials import GmailCredentials
from claude_evernote_sync.destinations import SyncContext
from claude_evernote_sync.email_client import EmailNote, send
from claude_evernote_sync.formatter import (
    note_title,
    render_email_html,
    render_new_messages_html,
)

logger = logging.getLogger(__name__)


@dataclass
class EmailDestination:
    creds: GmailCredentials

    def sync_group(self, ctx: SyncContext) -> set[str]:
        if not ctx.new_messages:
            logger.debug("no new messages for %s/%s", ctx.date_iso, ctx.bucket)
            return set()
        note = self._build_note(ctx)
        send(self.creds, note)
        return {m.uuid for m in ctx.new_messages}

    def _build_note(self, ctx: SyncContext) -> EmailNote:
        title = note_title(ctx.bucket, ctx.date_iso)
        if ctx.is_first_sync:
            html = render_email_html(ctx.date_iso, ctx.bucket, ctx.sessions)
            return EmailNote(title=title, html_body=html, append=False, notebook=ctx.notebook_name)
        html = render_new_messages_html(ctx.sessions_with_new)
        return EmailNote(title=title, html_body=html, append=True, notebook=ctx.notebook_name)
