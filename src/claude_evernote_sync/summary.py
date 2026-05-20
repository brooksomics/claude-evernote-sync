"""Extract and attach Claude Code's embedded session summaries.

Claude Code writes `{"type": "summary", "summary": ..., "leafUuid": ...}`
records into JSONL files for its own /resume UI. We can use these as
Evernote note titles without an extra LLM call.

`leafUuid` points to a message UUID. We match summaries to sessions
globally (across files) because Claude Code sometimes writes a summary
for session A into session B's file — see anthropics/claude-code#2597.
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


def attach_cross_file_summaries(sessions: list[Session], summaries: list[SummaryRecord]) -> None:
    """Match summaries to sessions via leafUuid → message_uuid → session.

    Mutates `Session.summary` in place. First match wins; subsequent
    matching records for the same session are ignored. Summaries whose
    leafUuid doesn't appear in any session are dropped silently.
    """
    uuid_to_session = {m.uuid: s for s in sessions for m in s.messages}
    for record in summaries:
        target = uuid_to_session.get(record.leaf_uuid)
        if target and target.summary is None:
            target.summary = record.summary


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
