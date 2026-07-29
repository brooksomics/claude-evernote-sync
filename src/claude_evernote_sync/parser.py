"""Parse Claude Code session JSONL files into Session objects."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_evernote_sync.agent_results import extract_agent_results, is_task_notification
from claude_evernote_sync.tool_calls import (
    ToolCall,
    extract_tool_calls,
    text_from_content,
    with_agent_results,
)

CONVERSATION_TYPES = {"user", "assistant"}
ANSI_CSI_RE = re.compile(r"\x1b\[[\d;]*[a-zA-Z]")
ANSI_SGR_BARE_RE = re.compile(r"\[\d+(?:;\d+)*m")
SLASH_COMMAND_PREFIXES = (
    "<local-command-caveat",
    "<local-command-stdout",
    "<command-name",
    "<command-message",
    "<command-args",
)


@dataclass(frozen=True)
class Message:
    uuid: str
    role: str
    text: str
    ts: datetime
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass
class Session:
    session_id: str
    cwd: str
    git_branch: str | None
    version: str | None
    start_ts: datetime
    end_ts: datetime
    messages: list[Message]
    summary: str | None = None

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def duration_seconds(self) -> int:
        return int((self.end_ts - self.start_ts).total_seconds())


def strip_ansi(text: str) -> str:
    """Remove ANSI CSI sequences and bare SGR brackets like `[1m...[22m`.

    Bare SGR appears when something upstream stripped the ESC byte but
    left the bracket sequence behind, which is what the user's archived
    notes showed in Evernote.
    """
    text = ANSI_CSI_RE.sub("", text)
    return ANSI_SGR_BARE_RE.sub("", text)


def is_slash_command_lifecycle(text: str) -> bool:
    """True if the text is a slash-command lifecycle wrapper that Claude Code
    emits as a 'user' record when a slash command runs. Filtering these keeps
    the archive focused on conversational content, not meta-actions."""
    stripped = text.lstrip()
    return any(stripped.startswith(p) for p in SLASH_COMMAND_PREFIXES)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _content_of(record: dict[str, Any]) -> Any:
    return (record.get("message") or {}).get("content")


def _extract_message(record: dict[str, Any]) -> Message | None:
    if record.get("type") not in CONVERSATION_TYPES:
        return None
    content = _content_of(record)
    text = text_from_content(content).strip()
    if is_slash_command_lifecycle(text) or is_task_notification(text):
        return None
    tool_calls = extract_tool_calls(content)
    if not text and not tool_calls:
        return None
    ts = _parse_timestamp(record["timestamp"])
    uuid = str(record.get("uuid") or f"{record.get('sessionId', '?')}:{ts.isoformat()}")
    return Message(
        uuid=uuid, role=record["type"], text=strip_ansi(text), ts=ts, tool_calls=tool_calls
    )


def _iter_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _first_value(records: list[dict[str, Any]], key: str) -> Any:
    for r in records:
        if r.get(key) is not None:
            return r[key]
    return None


def _append_or_merge(messages: list[Message], msg: Message) -> None:
    """Fold a tool-only assistant record into the preceding assistant message.

    Claude Code often splits one assistant turn across records (text in one,
    tool_use in the next). Merging keeps the message set — and the email
    append/state bookkeeping — identical to text-only parsing.
    """
    can_merge = (
        not msg.text
        and msg.role == "assistant"
        and bool(messages)
        and messages[-1].role == "assistant"
    )
    if can_merge:
        prev = messages[-1]
        messages[-1] = replace(prev, tool_calls=prev.tool_calls + msg.tool_calls)
    else:
        messages.append(msg)


def _build_session(path: Path, records: list[dict[str, Any]]) -> Session | None:
    messages: list[Message] = []
    for record in records:
        msg = _extract_message(record)
        if msg is not None:
            _append_or_merge(messages, msg)
    if not messages:
        return None
    return Session(
        session_id=path.stem,
        cwd=str(_first_value(records, "cwd") or ""),
        git_branch=_first_value(records, "gitBranch"),
        version=_first_value(records, "version"),
        start_ts=messages[0].ts,
        end_ts=messages[-1].ts,
        messages=messages,
    )


def _attach_agent_results(session: Session, records: list[dict[str, Any]]) -> None:
    """Pair each Agent call with the report from its task-notification.

    Reports are collected across the whole file first: the notification lands
    many records after the launch. The report attaches to the launch message,
    so a session already appended past that message before its agent finished
    keeps the findings out of the note.
    # ponytail: good enough while quiet_minutes gates on session end; key the
    # report to the notification's own timestamp if that stops holding.
    """
    results: dict[str, str] = {}
    for record in records:
        results.update(extract_agent_results(record))
    if not results:
        return
    session.messages[:] = [
        replace(m, tool_calls=with_agent_results(m.tool_calls, results)) for m in session.messages
    ]


def parse_jsonl_file(path: Path) -> Session | None:
    """Parse a Claude Code JSONL session file. Returns None if no usable content."""
    if not path.exists():
        return None
    records = list(_iter_records(path))
    session = _build_session(path, records)
    if session is not None:
        _attach_agent_results(session, records)
    return session
