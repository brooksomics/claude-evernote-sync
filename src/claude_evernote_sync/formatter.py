"""Render Claude Code sessions as ENML or plain HTML for email."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo

import markdown

from claude_evernote_sync.parser import Message, Session
from claude_evernote_sync.tables import style_tables
from claude_evernote_sync.tool_calls import ToolCall

ENML_PROLOGUE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">\n'
    "<en-note>\n"
)
ENML_EPILOGUE = "</en-note>\n"

ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&apos;"))

TITLE_MAX_LEN = 80

# Role -> (display label, inline text color). Evernote's email->ENML conversion
# strips background/border/padding, so role distinction rides on colored bold
# text rather than tinted boxes.
ROLE_STYLES = {"user": ("You", "#4f46e5"), "assistant": ("Claude", "#d97706")}


def xml_escape(text: str) -> str:
    """Escape characters reserved in XML/ENML."""
    out = text
    for original, replacement in ESCAPES:
        out = out.replace(original, replacement)
    return out


def _split_fenced(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_code, segment) parts, toggling on ``` fence lines.

    Fence lines (and any language tag) are dropped. Pairing is sequential and
    line-based, which avoids the orphaned-tag corruption a regex produces on
    messages with many or nested fences.
    """
    segments: list[tuple[bool, str]] = []
    buf: list[str] = []
    in_code = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            segments.append((in_code, "\n".join(buf)))
            buf, in_code = [], not in_code
        else:
            buf.append(line)
    segments.append((in_code, "\n".join(buf)))
    return segments


def _md(text: str) -> str:
    """Render prose markdown (bold, inline code, lists, tables, links) to safe XHTML."""
    html = markdown.markdown(
        xml_escape(text), output_format="xhtml", extensions=["nl2br", "tables"]
    )
    return style_tables(html)


def render_message_text(text: str) -> str:
    """Render message text: prose via markdown, fenced code as a once-escaped <pre>.

    Escaping fenced code ourselves (rather than letting markdown's fenced_code
    re-escape an already-escaped string) avoids the double-escape that turns
    `<` into a literal `&lt;`. <pre> monospace survives Evernote; highlight
    spans inside it do not, so we don't attempt them.
    """
    parts: list[str] = []
    for is_code, segment in _split_fenced(text):
        if is_code and segment.strip():
            parts.append(f"<pre>{xml_escape(segment)}</pre>")
        elif not is_code:
            parts.append(_md(segment))
    return "".join(parts)


def _render_tool_call(call: ToolCall) -> str:
    name = f"<code>{xml_escape(call.name)}</code>"
    if not call.summary:
        return f"<li>{name}</li>"
    return f"<li>{name} {xml_escape(call.summary)}</li>"


def render_tool_calls(calls: tuple[ToolCall, ...]) -> str:
    """Compact, foldable list of what the assistant did (tool name + brief arg).

    A nested <ul> under a small "tools" item: both survive Evernote's email
    conversion, and the parent item folds the calls away in the app.
    """
    items = "".join(_render_tool_call(c) for c in calls)
    label = '<span style="font-size:11px;color:#888">tools</span>'
    return f"<ul><li>{label}<ul>{items}</ul></li></ul>"


def note_title_for_session(session: Session, bucket: str) -> str:
    """Build a stable, ASCII-safe note title for one session.

    Priority for the topic part: session.summary, then the first user prompt
    (truncated), then a literal fallback. ASCII hyphens (not em-dashes) keep
    the SMTP Subject header unencoded so Evernote's `@notebook` parser sees
    a literal `@`. The short-id suffix guarantees uniqueness even when two
    sessions land on the same topic.
    """
    topic = (session.summary or _first_user_text(session) or "Claude Session").strip()
    topic = topic.replace("\n", " ").replace("\r", " ")
    if len(topic) > TITLE_MAX_LEN:
        topic = topic[:TITLE_MAX_LEN].rstrip() + "…"
    return f"{topic} - {bucket} - {session.session_id[:8]}"


def _first_user_text(session: Session) -> str:
    """First user message's prose (code fences excluded) for the title fallback."""
    for m in session.messages:
        if m.role != "user":
            continue
        prose = "\n".join(s for code, s in _split_fenced(m.text) if not code).strip()
        if prose:
            return prose
    return ""


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
    """Renders a single session to ENML / HTML in a configured display timezone."""

    timezone: tzinfo = field(default=UTC)
    content_depth: str = "full"

    def render_session_enml(self, session: Session) -> str:
        """ENML note (with prologue/epilogue) for the API destination."""
        return ENML_PROLOGUE + self._render_full_body(session) + "\n" + ENML_EPILOGUE

    def render_session_html(self, session: Session) -> str:
        """HTML body for the initial email-to-note (creates the note)."""
        return self._render_full_body(session)

    def render_new_messages_html(self, new_msgs: list[Message], now: datetime | None = None) -> str:
        """HTML body for an append email — only new messages, with timestamp marker."""
        stamp = self._fmt_time(now or datetime.now(UTC), "%H:%M")
        parts = ["<hr/>", f"<p><b>Update at {stamp}</b></p>"]
        parts.extend(self._render_message(m) for m in new_msgs)
        return "\n".join(parts)

    def _fmt_time(self, dt: datetime, fmt: str) -> str:
        local = dt.astimezone(self.timezone)
        return f"{local.strftime(fmt)} {local.tzname() or 'UTC'}"

    def _render_message(self, msg: Message) -> str:
        label, color = ROLE_STYLES.get(msg.role, ROLE_STYLES["assistant"])
        ts = self._fmt_time(msg.ts, "%H:%M")
        header = (
            f'<p><span style="color:{color};font-weight:bold">{label}</span> '
            f'<span style="font-size:11px;color:#888">{ts}</span></p>'
        )
        body = header + render_message_text(msg.text) if msg.text else ""
        if self.content_depth != "conversation" and msg.tool_calls:
            body += render_tool_calls(msg.tool_calls)
        return body

    def _render_session_meta(self, session: Session) -> str:
        start = session.start_ts.astimezone(self.timezone).strftime("%H:%M")
        end_label = self._fmt_time(session.end_ts, "%H:%M")
        meta = [
            f"path: {xml_escape(session.cwd)}",
            f"branch: {xml_escape(session.git_branch or '-')}",
            f"version: {xml_escape(session.version or '-')}",
            f"messages: {session.message_count}",
            f"id: {xml_escape(session.session_id[:8])}",
            f"{start}-{end_label}",
        ]
        return f'<p><span style="font-size:11px;color:#888">{" · ".join(meta)}</span></p>'

    def _render_full_body(self, session: Session) -> str:
        meta = self._render_session_meta(session)
        messages_html = "\n".join(self._render_message(m) for m in session.messages)
        return meta + "\n" + messages_html
