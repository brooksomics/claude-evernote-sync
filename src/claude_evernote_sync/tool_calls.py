"""Extract compact tool-call summaries from Claude Code message content.

A Claude Code assistant message's content is a list of blocks; `tool_use`
blocks record what the assistant did (Bash, Read, Edit, Task, ...). We keep a
one-line gloss per call so the rendered note shows the action trace without the
verbose tool *output* that made the raw logs unreadable.
"""

from __future__ import annotations

from dataclasses import dataclass

# Input keys to prefer (in order) for a one-line summary of a tool call.
SUMMARY_KEYS = ("description", "command", "file_path", "pattern", "url", "query", "prompt")


@dataclass(frozen=True)
class ToolCall:
    name: str
    summary: str


def _tool_summary(tool_input: object) -> str:
    """A short single-line gloss of a tool call's most salient argument."""
    if not isinstance(tool_input, dict):
        return ""
    for key in SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().split("\n", 1)[0][:100]
    return ""


def extract_tool_calls(content: object) -> tuple[ToolCall, ...]:
    """Pull (name, summary) for each tool_use block in a message's content."""
    if not isinstance(content, list):
        return ()
    return tuple(
        ToolCall(str(b.get("name", "tool")), _tool_summary(b.get("input")))
        for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use"
    )
