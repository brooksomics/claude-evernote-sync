"""Parse Claude Code session JSONL files into Session objects."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

CONVERSATION_TYPES = {"user", "assistant"}
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
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


def strip_code_fences(text: str) -> str:
    """Remove ```...``` fenced code blocks; keep inline `code` backticks."""
    return CODE_FENCE_RE.sub("", text)


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


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def _extract_message(record: dict[str, Any]) -> Message | None:
    if record.get("type") not in CONVERSATION_TYPES:
        return None
    msg = record.get("message") or {}
    text = _extract_text_from_content(msg.get("content"))
    text = strip_code_fences(text).strip()
    if not text or is_slash_command_lifecycle(text):
        return None
    text = strip_ansi(text)
    ts = _parse_timestamp(record["timestamp"])
    uuid = str(record.get("uuid") or f"{record.get('sessionId', '?')}:{ts.isoformat()}")
    return Message(uuid=uuid, role=record["type"], text=text, ts=ts)


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


def _build_session(path: Path, records: list[dict[str, Any]]) -> Session | None:
    messages = [m for m in (_extract_message(r) for r in records) if m]
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


def parse_jsonl_file(path: Path) -> Session | None:
    """Parse a Claude Code JSONL session file. Returns None if no usable content."""
    if not path.exists():
        return None
    records = list(_iter_records(path))
    return _build_session(path, records)
