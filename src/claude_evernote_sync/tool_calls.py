"""Read Claude Code message content blocks: tool calls and their results.

A Claude Code assistant message's content is a list of blocks; `tool_use`
blocks record what the assistant did (Bash, Read, Edit, Agent, ...). We keep a
one-line gloss per call so the rendered note shows the action trace without the
verbose tool *output* that made the raw logs unreadable.

`Agent` is the exception. A sub-agent reads far more than it reports and returns
a synthesis — roughly a thousand-to-one compression of what it read — so that
return is the densest content in a session. With sub-agent transcripts
suppressed it is also the only trace of what the agent actually found, so we
carry it on the call while still dropping every other tool's output.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# Input keys to prefer (in order) for a one-line summary of a tool call.
SUMMARY_KEYS = ("description", "command", "file_path", "pattern", "url", "query", "prompt")

AGENT_TOOL = "Agent"


@dataclass(frozen=True)
class ToolCall:
    name: str
    summary: str
    tool_use_id: str = ""
    result: str = ""


def text_from_content(content: object) -> str:
    """Concatenate the `text` blocks of a message/tool-result content value."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text"
    )


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
    """Pull (name, summary, id) for each tool_use block in a message's content."""
    if not isinstance(content, list):
        return ()
    return tuple(
        ToolCall(
            str(b.get("name", "tool")),
            _tool_summary(b.get("input")),
            str(b.get("id") or ""),
        )
        for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use"
    )


def with_agent_results(
    calls: tuple[ToolCall, ...], results: dict[str, str]
) -> tuple[ToolCall, ...]:
    """Fill in `result` for Agent calls whose return text is in `results`."""
    return tuple(
        replace(c, result=results.get(c.tool_use_id, ""))
        if c.name == AGENT_TOOL and not c.result
        else c
        for c in calls
    )
