"""Recover sub-agent findings from Claude Code task-notification records.

A background sub-agent's `tool_result` is launch metadata ("Async agent
launched successfully…", plus an internal agent id), never its report. The
report arrives later inside a `<task-notification>` block, linked back to the
Agent call by `<tool-use-id>`.

Claude Code writes the same notification into several record shapes — a
`queue-operation`, an `attachment`, and the delivered `user` message — so the
findings can appear more than once, at different depths, and sometimes
truncated. We therefore walk every string in a record and keep the longest
report per tool-use id.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

TASK_NOTIFICATION_TAG = "<task-notification>"

_BLOCK_RE = re.compile(r"<task-notification>(.*?)</task-notification>", re.DOTALL)
_ID_RE = re.compile(r"<tool-use-id>([^<]+)</tool-use-id>")
_RESULT_RE = re.compile(r"<result>(.*?)</result>", re.DOTALL)


def is_task_notification(text: str) -> bool:
    """True if `text` is a task-notification wrapper rather than real dialogue."""
    return TASK_NOTIFICATION_TAG in text


def _iter_strings(value: Any) -> Iterator[str]:
    """Yield every string anywhere inside a decoded JSONL record."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _blocks(text: str) -> Iterator[tuple[str, str]]:
    """Yield (tool_use_id, report) for each complete notification in `text`.

    Matching inside one notification block at a time stops a still-running
    agent's id from being paired with the next agent's report.
    """
    for block in _BLOCK_RE.findall(text):
        found_id = _ID_RE.search(block)
        found_result = _RESULT_RE.search(block)
        if found_id and found_result:
            yield found_id.group(1).strip(), found_result.group(1).strip()


def extract_agent_results(record: dict[str, Any]) -> dict[str, str]:
    """Map tool_use_id -> agent report for notifications anywhere in `record`."""
    out: dict[str, str] = {}
    for text in _iter_strings(record):
        if not is_task_notification(text):
            continue
        for tool_use_id, report in _blocks(text):
            if len(report) > len(out.get(tool_use_id, "")):
                out[tool_use_id] = report
    return out
