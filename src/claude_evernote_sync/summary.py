"""Extract and attach Claude Code's embedded session topic strings.

Two record types both serve as "what is this session about?" in different
Claude Code versions:

- `{"type": "summary", "summary": ..., "leafUuid": ...}` — the older /resume
  format; leafUuid points to a message uuid and may end up in the wrong
  session's file (anthropics/claude-code#2597), so matching is global.
- `{"type": "ai-title", "aiTitle": ..., "sessionId": ...}` — the current
  format used by the sidebar / sessions list. Keyed directly by sessionId,
  so no cross-file contamination concern.

ai-title is treated as more authoritative than summary because sessionId
keying is unambiguous and Claude Code updates it as the session evolves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from claude_evernote_sync.parser import Session


@dataclass(frozen=True)
class SummaryRecord:
    leaf_uuid: str
    summary: str


@dataclass(frozen=True)
class AiTitleRecord:
    session_id: str
    title: str


def extract_summary_records(path: Path) -> list[SummaryRecord]:
    """Read `type=summary` records from a JSONL file. Malformed lines are skipped."""
    out: list[SummaryRecord] = []
    if not path.exists():
        return out
    for record in _iter_records(path):
        if record.get("type") != "summary":
            continue
        leaf = record.get("leafUuid")
        summary = record.get("summary")
        if isinstance(leaf, str) and isinstance(summary, str):
            out.append(SummaryRecord(leaf_uuid=leaf, summary=summary))
    return out


def extract_ai_title_records(path: Path) -> list[AiTitleRecord]:
    """Read `type=ai-title` records from a JSONL file. Malformed lines are skipped."""
    out: list[AiTitleRecord] = []
    if not path.exists():
        return out
    for record in _iter_records(path):
        if record.get("type") != "ai-title":
            continue
        sid = record.get("sessionId")
        title = record.get("aiTitle")
        if isinstance(sid, str) and isinstance(title, str):
            out.append(AiTitleRecord(session_id=sid, title=title))
    return out


def attach_cross_file_summaries(sessions: list[Session], summaries: list[SummaryRecord]) -> None:
    """Match `type=summary` records to sessions via leafUuid → message_uuid → session.

    Mutates `Session.summary` in place. First match wins; subsequent
    matching records for the same session are ignored. Summaries whose
    leafUuid doesn't appear in any session are dropped silently.
    """
    uuid_to_session = {m.uuid: s for s in sessions for m in s.messages}
    for record in summaries:
        target = uuid_to_session.get(record.leaf_uuid)
        if target and target.summary is None:
            target.summary = record.summary


def attach_ai_titles(sessions: list[Session], ai_titles: list[AiTitleRecord]) -> None:
    """Match `type=ai-title` records to sessions by sessionId.

    Last record wins (Claude Code writes the title repeatedly, refining it
    as the session evolves). Overrides any prior `session.summary` because
    sessionId keying is more reliable than leafUuid matching.
    """
    by_id = {s.session_id: s for s in sessions}
    for record in ai_titles:
        target = by_id.get(record.session_id)
        if target:
            target.summary = record.title


def is_subagent_path(path: Path) -> bool:
    """True if a JSONL file is a Claude Code sub-agent transcript (under subagents/)."""
    return "subagents" in path.parts


def read_subagent_description(path: Path) -> str | None:
    """Read a sub-agent's sibling `.meta.json` description (its task topic).

    Claude Code writes `<stem>.meta.json` ({agentType, description, toolUseId})
    next to each `subagents/agent-*.jsonl`. Returns None for non-sub-agent files
    or a missing/invalid sidecar.
    """
    if not is_subagent_path(path):
        return None
    meta = path.with_suffix(".meta.json")
    if not meta.exists():
        return None
    try:
        data = json.loads(meta.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    desc = data.get("description") if isinstance(data, dict) else None
    return desc.strip() if isinstance(desc, str) and desc.strip() else None


def attach_subagent_descriptions(sessions: list[Session], paths: list[Path]) -> None:
    """Set each sub-agent session's summary to its `.meta.json` description.

    Sub-agent transcripts carry the parent's sessionId, so ai-title never
    matches them and the title would fall back to the verbose task prompt.
    The meta description is the right topic, so this runs last and wins.
    """
    by_stem = {p.stem: p for p in paths}
    for session in sessions:
        path = by_stem.get(session.session_id)
        desc = read_subagent_description(path) if path else None
        if desc:
            session.summary = desc


def _iter_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
