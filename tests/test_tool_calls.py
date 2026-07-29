"""Tests for tool-call extraction."""

from claude_evernote_sync.tool_calls import (
    ToolCall,
    extract_tool_calls,
    text_from_content,
    with_agent_results,
)


def test_extract_tool_calls_basic() -> None:
    content = [
        {"type": "text", "text": "hi"},
        {
            "type": "tool_use",
            "name": "Bash",
            "input": {"command": "ls", "description": "List files"},
        },
        {"type": "tool_use", "name": "Read", "input": {"file_path": "/x/models.py"}},
    ]
    assert extract_tool_calls(content) == (
        ToolCall("Bash", "List files"),
        ToolCall("Read", "/x/models.py"),
    )


def test_extract_tool_calls_prefers_description_over_command() -> None:
    content = [
        {"type": "tool_use", "name": "Bash", "input": {"command": "x", "description": "Run x"}}
    ]
    assert extract_tool_calls(content)[0].summary == "Run x"


def test_extract_tool_calls_summary_is_single_line_truncated() -> None:
    content = [{"type": "tool_use", "name": "Grep", "input": {"pattern": "a" * 200 + "\nsecond"}}]
    summary = extract_tool_calls(content)[0].summary
    assert "\n" not in summary
    assert len(summary) == 100


def test_extract_tool_calls_no_recognized_key_gives_empty_summary() -> None:
    content = [{"type": "tool_use", "name": "Weird", "input": {"foo": "bar"}}]
    assert extract_tool_calls(content) == (ToolCall("Weird", ""),)


def test_extract_tool_calls_missing_input_gives_empty_summary() -> None:
    assert extract_tool_calls([{"type": "tool_use", "name": "Bash"}]) == (ToolCall("Bash", ""),)


def test_extract_tool_calls_string_content_returns_empty() -> None:
    assert extract_tool_calls("just a string") == ()


def test_extract_tool_calls_ignores_text_and_thinking_blocks() -> None:
    content = [{"type": "text", "text": "hi"}, {"type": "thinking", "thinking": "hmm"}]
    assert extract_tool_calls(content) == ()


def test_extract_tool_calls_captures_tool_use_id() -> None:
    content = [
        {"type": "tool_use", "id": "toolu_1", "name": "Agent", "input": {"description": "R"}}
    ]
    assert extract_tool_calls(content)[0].tool_use_id == "toolu_1"


def test_with_agent_results_fills_agent_return_text() -> None:
    calls = (ToolCall("Agent", "Research X", "toolu_1"),)
    filled = with_agent_results(calls, {"toolu_1": "what it found"})
    assert filled[0].result == "what it found"


def test_with_agent_results_ignores_non_agent_tools() -> None:
    """Bash/Read/WebFetch output is the bulk of a transcript's noise; only an
    Agent's synthesised return earns space in the parent note."""
    calls = (ToolCall("Bash", "ls", "toolu_1"),)
    assert with_agent_results(calls, {"toolu_1": "a megabyte of stdout"})[0].result == ""


def test_with_agent_results_leaves_unmatched_agent_empty() -> None:
    calls = (ToolCall("Agent", "Research X", "toolu_9"),)
    assert with_agent_results(calls, {"toolu_1": "x"})[0].result == ""


def test_text_from_content_handles_missing_and_raw_content() -> None:
    assert text_from_content(None) == ""
    assert text_from_content("raw string") == "raw string"
