"""Email-to-Evernote destination (append-only, per-session)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from claude_evernote_sync.credentials import GmailCredentials
from claude_evernote_sync.destinations import SyncContext
from claude_evernote_sync.email_client import EmailNote, send
from claude_evernote_sync.formatter import Renderer

logger = logging.getLogger(__name__)


@dataclass
class EmailDestination:
    creds: GmailCredentials
    renderer: Renderer = field(default_factory=Renderer)

    def sync_session(self, ctx: SyncContext) -> set[str]:
        new_msgs = ctx.new_messages
        if not new_msgs:
            logger.debug("no new messages for %s", ctx.session.session_id[:8])
            return set()
        note = self._build_note(ctx)
        send(self.creds, note)
        return {m.uuid for m in new_msgs}

    def _build_note(self, ctx: SyncContext) -> EmailNote:
        nb = ctx.notebook_name
        if ctx.is_first_sync:
            html = self.renderer.render_session_html(ctx.session)
            return EmailNote(title=ctx.title, html_body=html, append=False, notebook=nb)
        html = self.renderer.render_new_messages_html(ctx.new_messages)
        return EmailNote(title=ctx.title, html_body=html, append=True, notebook=nb)
