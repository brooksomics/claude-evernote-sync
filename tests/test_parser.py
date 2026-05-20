"""Tests for the JSONL parser."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_evernote_sync.parser import (
    Message,
    Session,
    is_slash_command_lifecycle,
    parse_jsonl_file,
    strip_ansi,
    strip_code_fences,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_session() -> Session:
    result = parse_jsonl_file(FIXTURES / "sample_session.jsonl")
    assert result is not None
    return result


def test_session_id_from_filename(sample_session: Session) -> None:
    assert sample_session.session_id == "sample_session"


def test_extracts_cwd_from_messages(sample_session: Session) -> None:
    assert sample_session.cwd == "/Users/bubba/Documents/git/myrepo"


def test_extracts_git_branch(sample_session: Session) -> None:
    assert sample_session.git_branch == "main"


def test_extracts_version(sample_session: Session) -> None:
    assert sample_session.version == "1.0.108"


def test_keeps_only_user_and_assistant_text(sample_session: Session) -> None:
    roles = [m.role for m in sample_session.messages]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_strips_thinking_blocks(sample_session: Session) -> None:
    for m in sample_session.messages:
        assert "thinking" not in m.text.lower() or "Let me look" not in m.text


def test_strips_tool_use_blocks(sample_session: Session) -> None:
    for m in sample_session.messages:
        assert "tool_use" not in m.text
        assert "Read" not in m.text or m.role == "user"


def test_strips_tool_result_messages(sample_session: Session) -> None:
    user_texts = [m.text for m in sample_session.messages if m.role == "user"]
    assert "file contents" not in " ".join(user_texts)


def test_strips_fenced_code_blocks(sample_session: Session) -> None:
    full_text = " ".join(m.text for m in sample_session.messages)
    assert "def old()" not in full_text
    assert "```" not in full_text


def test_message_timestamps_are_datetimes(sample_session: Session) -> None:
    for m in sample_session.messages:
        assert isinstance(m.ts, datetime)
        assert m.ts.tzinfo == UTC


def test_start_and_end_timestamps(sample_session: Session) -> None:
    assert sample_session.start_ts == datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)
    assert sample_session.end_ts == datetime(2026, 5, 15, 10, 0, 35, tzinfo=UTC)


def test_message_count(sample_session: Session) -> None:
    assert sample_session.message_count == 4


def test_duration_seconds(sample_session: Session) -> None:
    assert sample_session.duration_seconds == 35


def test_empty_file_returns_none() -> None:
    result = parse_jsonl_file(FIXTURES / "empty.jsonl")
    assert result is None


def test_malformed_lines_are_skipped() -> None:
    result = parse_jsonl_file(FIXTURES / "malformed.jsonl")
    assert result is not None
    assert result.message_count == 2
    assert result.messages[0].text == "Valid line"
    assert result.messages[1].text == "Recovered"


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert parse_jsonl_file(tmp_path / "nonexistent.jsonl") is None


def test_strip_code_fences_simple() -> None:
    text = "Before\n```python\ndef x(): pass\n```\nAfter"
    assert strip_code_fences(text).strip() == "Before\n\nAfter"


def test_strip_code_fences_multiple() -> None:
    text = "A\n```\ncode1\n```\nB\n```\ncode2\n```\nC"
    result = strip_code_fences(text)
    assert "code1" not in result
    assert "code2" not in result
    assert "A" in result and "B" in result and "C" in result


def test_strip_code_fences_inline_backticks_kept() -> None:
    text = "Use the `foo` function."
    assert strip_code_fences(text) == text


def test_message_dataclass() -> None:
    m = Message(uuid="u1", role="user", text="hi", ts=datetime(2026, 1, 1, tzinfo=UTC))
    assert m.role == "user"
    assert m.text == "hi"
    assert m.uuid == "u1"


def test_message_uuid_from_record(sample_session: Session) -> None:
    uuids = [m.uuid for m in sample_session.messages]
    assert "u1" in uuids
    assert "u3" in uuids
    assert "a2" in uuids
    assert "a4" in uuids


def test_message_uuid_fallback_when_missing(tmp_path: Path) -> None:
    line = (
        '{"type": "user", "timestamp": "2026-05-15T10:00:00.000Z", '
        '"cwd": "/x", "sessionId": "abc", "message": {"role": "user", "content": "hi"}}\n'
    )
    p = tmp_path / "no_uuid.jsonl"
    p.write_text(line)
    result = parse_jsonl_file(p)
    assert result is not None
    assert result.messages[0].uuid.startswith("abc:")


def test_session_truncates_long_messages(tmp_path: Path) -> None:
    """Sessions with one very long assistant message should still parse."""
    big_text = "x" * 100_000
    line = (
        '{"type": "user", "uuid": "u1", "timestamp": "2026-05-15T10:00:00.000Z", '
        '"cwd": "/x", "sessionId": "s", "version": "1.0", "gitBranch": null, '
        f'"message": {{"role": "user", "content": "{big_text}"}}}}\n'
    )
    p = tmp_path / "big.jsonl"
    p.write_text(line)
    result = parse_jsonl_file(p)
    assert result is not None
    assert len(result.messages[0].text) == 100_000


def test_strip_ansi_full_csi_sequences() -> None:
    """ESC + [ + params + final byte gets removed (the classic ANSI CSI form)."""
    assert strip_ansi("\x1b[1mbold\x1b[22m text") == "bold text"
    assert strip_ansi("\x1b[33;1myellow bold\x1b[0m") == "yellow bold"


def test_strip_ansi_sgr_without_esc() -> None:
    """SGR brackets without the leading ESC byte (e.g. `[1m...[22m`) are removed.

    Some upstream stripper removes the ESC byte but leaves the SGR brackets,
    which is what the user's example showed in Evernote.
    """
    assert strip_ansi("[1mOpus 4.7[22m for max effort") == "Opus 4.7 for max effort"
    assert strip_ansi("[33;1myellow[0m and [1mbold[22m") == "yellow and bold"


def test_strip_ansi_preserves_unrelated_brackets() -> None:
    """Brackets that aren't SGR codes must not be stripped."""
    assert strip_ansi("array [1, 2, 3]") == "array [1, 2, 3]"
    assert strip_ansi("regex [a-z]+") == "regex [a-z]+"
    assert strip_ansi("[TODO] check this") == "[TODO] check this"


def test_strip_ansi_passes_through_clean_text() -> None:
    assert strip_ansi("") == ""
    assert strip_ansi("no codes at all") == "no codes at all"


def test_is_slash_command_lifecycle_caveat() -> None:
    text = (
        "<local-command-caveat>Caveat: messages below were generated"
        " by the user</local-command-caveat>"
    )
    assert is_slash_command_lifecycle(text)


def test_is_slash_command_lifecycle_name() -> None:
    assert is_slash_command_lifecycle("<command-name>/model</command-name>")


def test_is_slash_command_lifecycle_message() -> None:
    assert is_slash_command_lifecycle("<command-message>model</command-message>")


def test_is_slash_command_lifecycle_args() -> None:
    assert is_slash_command_lifecycle("<command-args></command-args>")


def test_is_slash_command_lifecycle_stdout() -> None:
    text = "<local-command-stdout>Set model to ...</local-command-stdout>"
    assert is_slash_command_lifecycle(text)


def test_normal_user_text_is_not_slash_command_lifecycle() -> None:
    assert not is_slash_command_lifecycle("Hello, can you help?")
    assert not is_slash_command_lifecycle("I want to discuss this")
    assert not is_slash_command_lifecycle("Use <abc> in your response")
    assert not is_slash_command_lifecycle("")


def test_parser_drops_slash_command_lifecycle_messages(tmp_path: Path) -> None:
    """The 3-4 user messages that make up a slash-command invocation must not
    appear in Session.messages; only the user's real conversational input."""
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s",'
        '"message":{"role":"user","content":"<local-command-caveat>x</local-command-caveat>"}}',
        '{"type":"user","uuid":"u2","timestamp":"2026-05-15T10:00:00.001Z",'
        '"cwd":"/x","sessionId":"s",'
        '"message":{"role":"user","content":"<command-name>/model</command-name>"}}',
        '{"type":"user","uuid":"u3","timestamp":"2026-05-15T10:00:00.002Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":'
        '"<local-command-stdout>set to opus</local-command-stdout>"}}',
        '{"type":"user","uuid":"u4","timestamp":"2026-05-15T10:00:01.000Z",'
        '"cwd":"/x","sessionId":"s",'
        '"message":{"role":"user","content":"the real question"}}',
    ]
    p = tmp_path / "slash.jsonl"
    p.write_text("\n".join(lines))
    result = parse_jsonl_file(p)
    assert result is not None
    assert result.message_count == 1
    assert result.messages[0].text == "the real question"


def test_parser_strips_ansi_from_message_text(tmp_path: Path) -> None:
    """ANSI escape sequences embedded in message content are removed at parse time."""
    line = (
        '{"type":"assistant","uuid":"a1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s",'
        '"message":{"role":"assistant","content":"Set to [1mfoo[22m mode."}}'
    )
    p = tmp_path / "ansi.jsonl"
    p.write_text(line)
    result = parse_jsonl_file(p)
    assert result is not None
    assert result.messages[0].text == "Set to foo mode."


def test_session_summary_defaults_to_none(sample_session: Session) -> None:
    assert sample_session.summary is None
