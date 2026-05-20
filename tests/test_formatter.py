"""Tests for per-session ENML / HTML rendering."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from claude_evernote_sync.formatter import (
    Renderer,
    note_title_for_session,
    resolve_timezone,
    xml_escape,
)
from claude_evernote_sync.parser import Message, Session

LA = ZoneInfo("America/Los_Angeles")


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
            _msg("user", "Hello, can you help refactor this?", 10, 0),
            _msg("assistant", "Of course!", 10, 1),
            _msg("user", "Thanks", 10, 5),
        ],
    )


@pytest.fixture
def renderer() -> Renderer:
    return Renderer()


def test_note_title_uses_summary_when_present() -> None:
    s = _session("abc12345", "/x", [_msg("user", "first prompt", 10)])
    s.summary = "Refactor user auth"
    assert note_title_for_session(s, "myrepo") == "Refactor user auth - myrepo - abc12345"


def test_note_title_falls_back_to_first_user_prompt() -> None:
    s = _session("abc12345", "/x", [_msg("user", "Help me debug X", 10)])
    title = note_title_for_session(s, "myrepo")
    assert title == "Help me debug X - myrepo - abc12345"


def test_note_title_fallback_when_no_user_text() -> None:
    s = _session("abc12345", "/x", [_msg("assistant", "hi", 10)])
    title = note_title_for_session(s, "myrepo")
    assert title == "Claude Session - myrepo - abc12345"


def test_note_title_is_ascii_safe() -> None:
    """ASCII hyphens (not em-dashes) keep the SMTP Subject header unencoded so
    Evernote's @notebook parser sees a literal @."""
    s = _session("abc12345", "/x", [_msg("user", "plain ascii", 10)])
    title = note_title_for_session(s, "myrepo")
    title.encode("ascii")  # raises if non-ASCII slips in


def test_note_title_truncates_long_topic() -> None:
    s = _session("abc12345", "/x", [_msg("user", "x" * 200, 10)])
    title = note_title_for_session(s, "repo")
    assert "…" in title
    assert title.endswith(" - repo - abc12345")


def test_note_title_collapses_newlines_in_summary() -> None:
    s = _session("abc12345", "/x", [_msg("user", "hi", 10)])
    s.summary = "Line one\nline two"
    title = note_title_for_session(s, "r")
    assert "\n" not in title
    assert "Line one line two" in title


def test_xml_escape_basics() -> None:
    assert xml_escape("a & b") == "a &amp; b"
    assert xml_escape("<x>") == "&lt;x&gt;"
    assert xml_escape('say "hi"') == "say &quot;hi&quot;"
    assert xml_escape("she's") == "she&apos;s"


def test_resolve_timezone_utc() -> None:
    assert resolve_timezone("UTC") is UTC
    assert resolve_timezone("utc") is UTC


def test_resolve_timezone_iana() -> None:
    tz = resolve_timezone("America/Los_Angeles")
    assert tz.utcoffset(datetime(2026, 5, 15, 12, 0, tzinfo=UTC)).total_seconds() == -7 * 3600


def test_resolve_timezone_local_returns_some_tz() -> None:
    tz = resolve_timezone("local")
    assert tz is not None


def test_resolve_timezone_invalid_raises() -> None:
    from zoneinfo import ZoneInfoNotFoundError

    with pytest.raises(ZoneInfoNotFoundError):
        resolve_timezone("Not/A_Real_TZ")


def test_render_session_enml_wrapped(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_session_enml(simple_session, "Topic - repo - sessionab")
    assert enml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<!DOCTYPE en-note" in enml
    assert "<en-note>" in enml
    assert enml.rstrip().endswith("</en-note>")


def test_render_session_enml_includes_messages(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_session_enml(simple_session, "Topic")
    assert "Hello, can you help refactor this?" in enml
    assert "Of course!" in enml
    assert "Thanks" in enml


def test_render_session_html_starts_with_title_heading(
    renderer: Renderer, simple_session: Session
) -> None:
    html = renderer.render_session_html(simple_session, "My Topic")
    assert "<h1>My Topic</h1>" in html


def test_render_session_html_no_enml_wrapper(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_session_html(simple_session, "Topic")
    assert "<?xml" not in html
    assert "<en-note>" not in html


def test_render_session_html_includes_meta(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_session_html(simple_session, "Topic")
    assert "/Users/bubba/Documents/git/myrepo" in html
    assert "main" in html
    assert "1.0.108" in html
    assert "messages: 3" in html.lower()
    assert "session-" in html


def test_render_escapes_html_in_messages(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "<script>alert('xss')</script>", 10)])
    html = renderer.render_session_html(s, "Topic")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_escapes_html_in_title(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_session_html(simple_session, "<script>")
    assert "<h1><script>" not in html
    assert "<h1>&lt;script&gt;</h1>" in html


def test_render_converts_bold_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "This is **bold** text.", 10)])
    html = renderer.render_session_html(s, "Topic")
    assert "<strong>bold</strong>" in html


def test_render_converts_italic_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "An *italic* phrase.", 10)])
    html = renderer.render_session_html(s, "Topic")
    assert "<em>italic</em>" in html


def test_render_converts_inline_code_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "Use `foo()` to call.", 10)])
    html = renderer.render_session_html(s, "Topic")
    assert "<code>foo()</code>" in html


def test_render_converts_link_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "See [the docs](https://example.com).", 10)])
    html = renderer.render_session_html(s, "Topic")
    assert '<a href="https://example.com">the docs</a>' in html


def test_render_preserves_newlines_as_br(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("assistant", "line one\nline two", 10)])
    html = renderer.render_session_html(s, "Topic")
    assert "<br" in html


def test_render_new_messages_includes_update_marker_utc(renderer: Renderer) -> None:
    new_msg = _msg("assistant", "new content", 14, 30)
    now = datetime(2026, 5, 15, 14, 30, tzinfo=UTC)
    html = renderer.render_new_messages_html([new_msg], now=now)
    assert "Update at 14:30 UTC" in html
    assert "new content" in html


def test_render_new_messages_uses_configured_timezone() -> None:
    new_msg = _msg("user", "hi", 14, 30)
    now = datetime(2026, 5, 15, 14, 30, tzinfo=UTC)  # 07:30 PDT
    html = Renderer(timezone=LA).render_new_messages_html([new_msg], now=now)
    assert "Update at 07:30 PDT" in html


def test_message_timestamp_uses_configured_timezone() -> None:
    s = _session("s", "/x", [_msg("user", "hi", 18)])  # 18:00 UTC = 11:00 PDT
    html = Renderer(timezone=LA).render_session_html(s, "Topic")
    assert "11:00:00 PDT" in html


def test_session_meta_time_range_uses_configured_timezone() -> None:
    s = _session("s", "/x", [_msg("user", "hi", 17), _msg("assistant", "bye", 18)])
    html = Renderer(timezone=LA).render_session_html(s, "Topic")
    assert "10:00-11:00 PDT" in html


def test_utc_renderer_unchanged_format() -> None:
    s = _session("s", "/x", [_msg("user", "hi", 14)])
    html = Renderer().render_session_html(s, "Topic")
    assert "14:00:00 UTC" in html
