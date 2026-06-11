"""Tests for per-session ENML / HTML rendering."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from claude_evernote_sync.formatter import (
    Renderer,
    note_title_for_session,
    render_message_text,
    resolve_timezone,
    xml_escape,
)
from claude_evernote_sync.parser import Message, Session
from claude_evernote_sync.tool_calls import ToolCall

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
    enml = renderer.render_session_enml(simple_session)
    assert enml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<!DOCTYPE en-note" in enml
    assert "<en-note>" in enml
    assert enml.rstrip().endswith("</en-note>")


def test_render_session_enml_includes_messages(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_session_enml(simple_session)
    assert "Hello, can you help refactor this?" in enml
    assert "Of course!" in enml
    assert "Thanks" in enml


def test_render_session_html_omits_duplicate_title(
    renderer: Renderer, simple_session: Session
) -> None:
    """The Evernote note title already shows above the body; don't repeat it as an <h1>."""
    html = renderer.render_session_html(simple_session)
    assert "<h1>" not in html


def test_render_session_html_no_enml_wrapper(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_session_html(simple_session)
    assert "<?xml" not in html
    assert "<en-note>" not in html


def test_render_session_html_includes_meta(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_session_html(simple_session)
    assert "/Users/bubba/Documents/git/myrepo" in html
    assert "main" in html
    assert "1.0.108" in html
    assert "messages: 3" in html.lower()
    assert "session-" in html


def test_render_meta_uses_small_gray_not_italic(
    renderer: Renderer, simple_session: Session
) -> None:
    """Metadata is de-emphasized with survivor styling (small + gray), not <i> italics."""
    html = renderer.render_session_html(simple_session)
    assert "font-size:11px" in html
    assert "color:#888" in html


def test_render_uses_colored_you_and_claude_role_labels(
    renderer: Renderer, simple_session: Session
) -> None:
    html = renderer.render_session_html(simple_session)
    assert 'font-weight:bold">You</span>' in html
    assert 'font-weight:bold">Claude</span>' in html
    assert "#4f46e5" in html  # You (indigo)
    assert "#d97706" in html  # Claude (amber)


def test_render_escapes_html_in_messages(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "<script>alert('xss')</script>", 10)])
    html = renderer.render_session_html(s)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_converts_bold_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "This is **bold** text.", 10)])
    html = renderer.render_session_html(s)
    assert "<strong>bold</strong>" in html


def test_render_converts_italic_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "An *italic* phrase.", 10)])
    html = renderer.render_session_html(s)
    assert "<em>italic</em>" in html


def test_render_converts_inline_code_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "Use `foo()` to call.", 10)])
    html = renderer.render_session_html(s)
    assert "<code>foo()</code>" in html


def test_render_converts_link_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "See [the docs](https://example.com).", 10)])
    html = renderer.render_session_html(s)
    assert '<a href="https://example.com">the docs</a>' in html


PIPE_TABLE = "| # | Action | Cost |\n|---|---|---|\n| 1 | Term life | $170/mo |"


def test_render_converts_pipe_table_to_html_table() -> None:
    html = render_message_text(PIPE_TABLE)
    assert "<table" in html
    assert "<th" in html and "Action" in html
    assert "<td" in html and "$170/mo" in html
    assert "|---|" not in html


def test_render_table_has_visible_borders() -> None:
    html = render_message_text(PIPE_TABLE)
    assert '<table style="border-collapse:collapse">' in html
    assert html.count("border:1px solid") >= 6  # every th and td


def test_render_table_keeps_column_alignment_with_borders() -> None:
    html = render_message_text("| Left | Right |\n|:---|---:|\n| a | b |")
    assert '<th style="border:1px solid #ccc;padding:2px 8px;text-align:left">' in html
    assert '<td style="border:1px solid #ccc;padding:2px 8px;text-align:right">' in html


def test_render_table_cells_still_escaped() -> None:
    html = render_message_text("| H |\n|---|\n| <b>x</b> |")
    assert "<td" in html
    assert "<b>" not in html
    assert "&lt;b&gt;" in html


def test_render_table_inside_message(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("assistant", f"Summary:\n\n{PIPE_TABLE}\n\nDone.", 10)])
    html = renderer.render_session_html(s)
    assert "<table" in html
    assert "<p>Summary:</p>" in html


def test_render_preserves_newlines_as_br(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("assistant", "line one\nline two", 10)])
    html = renderer.render_session_html(s)
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
    html = Renderer(timezone=LA).render_session_html(s)
    assert "11:00 PDT" in html


def test_message_timestamp_is_minute_precision_no_seconds() -> None:
    s = _session("s", "/x", [_msg("user", "hi", 14)])
    html = Renderer().render_session_html(s)
    assert "14:00 UTC" in html
    assert "14:00:00" not in html


def test_session_meta_time_range_uses_configured_timezone() -> None:
    s = _session("s", "/x", [_msg("user", "hi", 17), _msg("assistant", "bye", 18)])
    html = Renderer(timezone=LA).render_session_html(s)
    assert "10:00-11:00 PDT" in html


def test_render_fenced_code_as_pre(renderer: Renderer) -> None:
    text = "Here:\n```python\ndef f():\n    pass\n```\ndone"
    s = _session("s", "/x", [_msg("assistant", text, 10)])
    html = renderer.render_session_html(s)
    assert "<pre>" in html
    assert "def f():" in html
    assert "```" not in html  # fence markers consumed
    assert "\npython\n" not in html  # language tag dropped, not orphaned


def test_render_fenced_code_preserves_indentation(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("assistant", "```\nif x:\n    go()\n```", 10)])
    html = renderer.render_session_html(s)
    assert "    go()" in html  # 4-space indent preserved inside <pre>


def test_render_fenced_code_escaped_exactly_once(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "```\nif a < b & c:\n    pass\n```", 10)])
    html = renderer.render_session_html(s)
    assert "&lt;" in html
    assert "&amp;" in html
    assert "&amp;lt;" not in html  # not double-escaped


def test_render_prose_html_still_escaped_when_code_present(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "<script>x</script>\n```\ncode\n```", 10)])
    html = renderer.render_session_html(s)
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_note_title_skips_code_in_fallback() -> None:
    s = _session(
        "abc12345", "/x", [_msg("user", "```\ncode_not_title\n```\nReal question here", 10)]
    )
    title = note_title_for_session(s, "repo")
    assert "code_not_title" not in title
    assert "Real question here" in title


def _assistant_with_tools() -> Session:
    ts = datetime(2026, 5, 15, 10, tzinfo=UTC)
    m = Message("a1", "assistant", "Let me look.", ts, tool_calls=(ToolCall("Bash", "git status"),))
    return _session("s", "/x", [m])


def test_render_full_shows_compact_tool_calls(renderer: Renderer) -> None:
    html = renderer.render_session_html(_assistant_with_tools())
    assert "<code>Bash</code>" in html
    assert "git status" in html
    assert "<ul>" in html  # foldable list


def test_render_conversation_hides_tool_calls() -> None:
    html = Renderer(content_depth="conversation").render_session_html(_assistant_with_tools())
    assert "Let me look." in html  # dialogue still rendered
    assert "<code>Bash</code>" not in html
    assert "git status" not in html


def test_render_tool_call_without_summary_omits_trailing_space(renderer: Renderer) -> None:
    ts = datetime(2026, 5, 15, 10, tzinfo=UTC)
    m = Message("a1", "assistant", "go", ts, tool_calls=(ToolCall("TodoWrite", ""),))
    html = renderer.render_session_html(_session("s", "/x", [m]))
    assert "<li><code>TodoWrite</code></li>" in html
