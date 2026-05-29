"""Tests for tool-call extraction."""

from claude_evernote_sync.tool_calls import ToolCall, extract_tool_calls


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
