"""Tests for the JSONL parser."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_evernote_sync.parser import (
    Message,
    Session,
    parse_jsonl_file,
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
