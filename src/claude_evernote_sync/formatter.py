"""Render Claude Code sessions as ENML or plain HTML for email."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

from claude_evernote_sync.parser import Message, Session

ENML_PROLOGUE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">\n'
    "<en-note>\n"
)
ENML_EPILOGUE = "</en-note>\n"

ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&apos;"))


def xml_escape(text: str) -> str:
    """Escape characters reserved in XML/ENML."""
    out = text
    for original, replacement in ESCAPES:
        out = out.replace(original, replacement)
    return out


def note_title(bucket: str, date_iso: str) -> str:
    """Build the canonical note title for a (bucket, date) pair.

    Separators are ASCII hyphens, not em-dashes. Non-ASCII chars in the SMTP
    Subject header trigger RFC 2047 quoted-printable encoding of the whole
    header, which encodes the `@` and `+` directives as `=40` and `=2B`.
    Evernote's email-to-note parser scans the raw header for a literal `@`,
    fails to find it, and silently routes the email to the default notebook
    instead of the one named after `@`.
    """
    return f"Claude Sessions - {bucket} - {date_iso}"


def resolve_timezone(tz_str: str) -> tzinfo:
    """Parse a config-style timezone string to a tzinfo.

    Accepts:
      - "UTC" (case-insensitive) → UTC
      - "local" → the system's current timezone
      - any IANA name like "America/Los_Angeles" → ZoneInfo(name)
    Raises ZoneInfoNotFoundError for invalid IANA names.
    """
    lowered = tz_str.lower()
    if lowered == "utc":
        return UTC
    if lowered == "local":
        local = datetime.now().astimezone().tzinfo
        return local or UTC
    return ZoneInfo(tz_str)


@dataclass
class Renderer:
    """Renders sessions to ENML / HTML in a configured display timezone."""

    timezone: tzinfo = field(default=UTC)

    def render_group(self, date_iso: str, bucket: str, sessions: list[Session]) -> str:
        """ENML note (with prologue/epilogue) for the API destination."""
        return ENML_PROLOGUE + self._render_body(date_iso, bucket, sessions) + "\n" + ENML_EPILOGUE

    def render_email_html(self, date_iso: str, bucket: str, sessions: list[Session]) -> str:
        """Plain HTML body for an initial email-to-note (creates note)."""
        return self._render_body(date_iso, bucket, sessions)

    def render_new_messages_html(
        self,
        sessions_with_new: list[tuple[Session, list[Message]]],
        now: datetime | None = None,
    ) -> str:
        """HTML body for an append email — only new messages, with timestamp marker."""
        stamp = self._fmt_time(now or datetime.now(UTC), "%H:%M")
        parts = ["<hr/>", f"<p><b>Update at {stamp}</b></p>"]
        for session, new_msgs in sessions_with_new:
            if not new_msgs:
                continue
            parts.append(self._render_session_header(session))
            parts.extend(self._render_message(m) for m in new_msgs)
        return "\n".join(parts)

    def _fmt_time(self, dt: datetime, fmt: str) -> str:
        local = dt.astimezone(self.timezone)
        return f"{local.strftime(fmt)} {local.tzname() or 'UTC'}"

    def _render_message(self, msg: Message) -> str:
        role_label = "User" if msg.role == "user" else "Assistant"
        ts = self._fmt_time(msg.ts, "%H:%M:%S")
        header = f"<p><b>{role_label}</b> <i>({ts})</i></p>"
        body = "<p>" + "<br/>".join(xml_escape(msg.text).split("\n")) + "</p>"
        return header + body

    def _render_session_header(self, session: Session) -> str:
        start = session.start_ts.astimezone(self.timezone).strftime("%H:%M")
        end_label = self._fmt_time(session.end_ts, "%H:%M")
        meta = [
            f"path: {xml_escape(session.cwd)}",
            f"branch: {xml_escape(session.git_branch or '-')}",
            f"version: {xml_escape(session.version or '-')}",
            f"messages: {session.message_count}",
        ]
        header = f"<b>Session {xml_escape(session.session_id[:8])}</b>"
        time_range = f"<i>{start}-{end_label}</i>"
        return f"<hr/><p>{header} · {time_range}</p><p><i>{' · '.join(meta)}</i></p>"

    def _render_body(self, date_iso: str, bucket: str, sessions: list[Session]) -> str:
        title = note_title(bucket, date_iso)
        heading = f"<h1>{xml_escape(title)}</h1>"
        sessions_html = "\n".join(
            self._render_session_header(s)
            + "\n"
            + "\n".join(self._render_message(m) for m in s.messages)
            for s in sessions
        )
        return heading + "\n" + sessions_html
