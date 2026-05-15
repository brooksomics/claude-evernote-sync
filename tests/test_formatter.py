"""Tests for ENML rendering of session groups."""

from datetime import UTC, datetime

import pytest

from claude_evernote_sync.formatter import (
    note_title,
    render_email_html,
    render_group,
    render_new_messages_html,
    xml_escape,
)
from claude_evernote_sync.parser import Message, Session


def _msg(role: str, text: str, h: int, m: int = 0) -> Message:
    ts = datetime(2026, 5, 15, h, m, tzinfo=UTC)
    return Message(uuid=f"u-{role}-{h}-{m}", role=role, text=text, ts=ts)


def _session(session_id: str, cwd: str, messages: list[Message]) -> Session:
    return Session(
        session_id=session_id,
        cwd=cwd,
        git_branch="main",
        version="1.0.108",
        start_ts=messages[0].ts,
        end_ts=messages[-1].ts,
        messages=messages,
    )


@pytest.fixture
def simple_session() -> Session:
    return _session(
        "session-abc",
        "/Users/bubba/Documents/git/myrepo",
        [
            _msg("user", "Hello, can you help?", 10, 0),
            _msg("assistant", "Of course!", 10, 1),
            _msg("user", "Thanks", 10, 5),
        ],
    )


def test_note_title_format() -> None:
    assert note_title("myrepo", "2026-05-15") == "Claude Sessions — myrepo — 2026-05-15"


def test_note_title_handles_special_chars() -> None:
    assert "TileDB-Documentation" in note_title("TileDB-Documentation", "2026-05-15")


def test_xml_escape_basics() -> None:
    assert xml_escape("a & b") == "a &amp; b"
    assert xml_escape("<x>") == "&lt;x&gt;"
    assert xml_escape('say "hi"') == "say &quot;hi&quot;"
    assert xml_escape("she's") == "she&apos;s"


def test_render_group_valid_enml(simple_session: Session) -> None:
    enml = render_group("2026-05-15", "myrepo", [simple_session])
    assert enml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<!DOCTYPE en-note" in enml
    assert "<en-note>" in enml
    assert enml.rstrip().endswith("</en-note>")


def test_render_group_includes_messages(simple_session: Session) -> None:
    enml = render_group("2026-05-15", "myrepo", [simple_session])
    assert "Hello, can you help?" in enml
    assert "Of course!" in enml
    assert "Thanks" in enml


def test_render_group_role_labels(simple_session: Session) -> None:
    enml = render_group("2026-05-15", "myrepo", [simple_session])
    assert "User" in enml
    assert "Assistant" in enml


def test_render_group_session_header_metadata(simple_session: Session) -> None:
    enml = render_group("2026-05-15", "myrepo", [simple_session])
    assert "/Users/bubba/Documents/git/myrepo" in enml
    assert "main" in enml
    assert "1.0.108" in enml
    assert "messages: 3" in enml.lower()


def test_render_group_escapes_html_in_messages() -> None:
    s = _session("s1", "/x", [_msg("user", "<script>alert('xss')</script>", 10)])
    enml = render_group("2026-05-15", "x", [s])
    assert "<script>" not in enml
    assert "&lt;script&gt;" in enml


def test_render_group_multiple_sessions_appear_in_time_order() -> None:
    s1 = _session("first", "/x", [_msg("user", "first session", 9)])
    s2 = _session("second", "/x", [_msg("user", "second session", 14)])
    enml = render_group("2026-05-15", "x", [s1, s2])
    assert enml.index("first session") < enml.index("second session")


def test_render_group_includes_date_header() -> None:
    s = _session("s1", "/x", [_msg("user", "hi", 10)])
    enml = render_group("2026-05-15", "myrepo", [s])
    assert "2026-05-15" in enml
    assert "myrepo" in enml


def test_render_group_preserves_newlines_in_messages() -> None:
    s = _session(
        "s1",
        "/x",
        [_msg("user", "line one\n\nline two", 10)],
    )
    enml = render_group("2026-05-15", "x", [s])
    assert "line one" in enml
    assert "line two" in enml
    assert "<br" in enml or "<p" in enml


def test_render_group_empty_list_returns_valid_enml() -> None:
    enml = render_group("2026-05-15", "empty", [])
    assert "<en-note>" in enml
    assert "</en-note>" in enml


def test_render_email_html_no_enml_wrapper(simple_session: Session) -> None:
    html = render_email_html("2026-05-15", "myrepo", [simple_session])
    assert "<?xml" not in html
    assert "<en-note>" not in html
    assert "<h1>" in html


def test_render_email_html_includes_content(simple_session: Session) -> None:
    html = render_email_html("2026-05-15", "myrepo", [simple_session])
    assert "Hello, can you help?" in html
    assert "myrepo" in html
    assert "2026-05-15" in html


def test_render_new_messages_includes_update_marker() -> None:
    s = _session("s1", "/x", [_msg("user", "old", 9), _msg("assistant", "new", 14)])
    new_msgs = [s.messages[1]]
    now = datetime(2026, 5, 15, 14, 30, tzinfo=UTC)
    html = render_new_messages_html([(s, new_msgs)], now=now)
    assert "Update at 14:30 UTC" in html
    assert "new" in html
    assert "old" not in html


def test_render_new_messages_skips_sessions_with_no_new() -> None:
    s1 = _session("s1", "/x", [_msg("user", "alpha", 9)])
    s2 = _session("s2", "/x", [_msg("user", "beta", 10)])
    now = datetime(2026, 5, 15, 11, 0, tzinfo=UTC)
    html = render_new_messages_html([(s1, []), (s2, s2.messages)], now=now)
    assert "alpha" not in html
    assert "beta" in html


def test_render_new_messages_includes_session_header() -> None:
    s = _session("s1", "/x/myrepo", [_msg("user", "hi", 10)])
    now = datetime(2026, 5, 15, 11, 0, tzinfo=UTC)
    html = render_new_messages_html([(s, s.messages)], now=now)
    assert "/x/myrepo" in html


def test_render_new_messages_default_now_is_real_time() -> None:
    s = _session("s1", "/x", [_msg("user", "hi", 10)])
    html = render_new_messages_html([(s, s.messages)])
    assert "Update at" in html
