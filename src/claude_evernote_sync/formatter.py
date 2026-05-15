"""Render Claude Code sessions as ENML or plain HTML for email."""

from __future__ import annotations

from datetime import UTC, datetime

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


def _render_paragraph(text: str) -> str:
    escaped = xml_escape(text)
    lines = escaped.split("\n")
    return "<p>" + "<br/>".join(lines) + "</p>"


def _render_message(msg: Message) -> str:
    role_label = "User" if msg.role == "user" else "Assistant"
    ts = msg.ts.strftime("%H:%M:%S UTC")
    header = f"<p><b>{role_label}</b> <i>({ts})</i></p>"
    return header + _render_paragraph(msg.text)


def _render_session_header(session: Session) -> str:
    parts = [
        f"<b>Session {xml_escape(session.session_id[:8])}</b>",
        f"<i>{session.start_ts.strftime('%H:%M')}-{session.end_ts.strftime('%H:%M UTC')}</i>",
    ]
    meta = [
        f"path: {xml_escape(session.cwd)}",
        f"branch: {xml_escape(session.git_branch or '-')}",
        f"version: {xml_escape(session.version or '-')}",
        f"messages: {session.message_count}",
    ]
    return f"<hr/><p>{' · '.join(parts)}</p><p><i>{' · '.join(meta)}</i></p>"


def _render_body(date_iso: str, bucket: str, sessions: list[Session]) -> str:
    title = note_title(bucket, date_iso)
    heading = f"<h1>{xml_escape(title)}</h1>"
    sessions_html = "\n".join(
        _render_session_header(s) + "\n" + "\n".join(_render_message(m) for m in s.messages)
        for s in sessions
    )
    return heading + "\n" + sessions_html


def render_group(date_iso: str, bucket: str, sessions: list[Session]) -> str:
    """Render all sessions for a (date, bucket) group as a complete ENML note."""
    return ENML_PROLOGUE + _render_body(date_iso, bucket, sessions) + "\n" + ENML_EPILOGUE


def render_email_html(date_iso: str, bucket: str, sessions: list[Session]) -> str:
    """Render full HTML body for an initial email-to-note (creates note)."""
    return _render_body(date_iso, bucket, sessions)


def render_new_messages_html(
    sessions_with_new: list[tuple[Session, list[Message]]],
    now: datetime | None = None,
) -> str:
    """Render HTML body for an append email — only new messages, with timestamp marker."""
    stamp = (now or datetime.now(UTC)).strftime("%H:%M UTC")
    parts = ["<hr/>", f"<p><b>Update at {stamp}</b></p>"]
    for session, new_msgs in sessions_with_new:
        if not new_msgs:
            continue
        parts.append(_render_session_header(session))
        parts.extend(_render_message(m) for m in new_msgs)
    return "\n".join(parts)
