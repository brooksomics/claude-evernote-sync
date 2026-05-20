"""Tests for ENML rendering of session groups."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from claude_evernote_sync.formatter import (
    Renderer,
    note_title,
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
            _msg("user", "Hello, can you help?", 10, 0),
            _msg("assistant", "Of course!", 10, 1),
            _msg("user", "Thanks", 10, 5),
        ],
    )


@pytest.fixture
def renderer() -> Renderer:
    return Renderer()


def test_note_title_format() -> None:
    """Separator must be ASCII hyphen, not em-dash, to keep the SMTP Subject
    header unencoded so Evernote's @notebook parser can see the literal `@`."""
    assert note_title("myrepo", "2026-05-15") == "Claude Sessions - myrepo - 2026-05-15"


def test_note_title_is_ascii_only() -> None:
    title = note_title("myrepo", "2026-05-15")
    title.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII slips in


def test_note_title_handles_special_chars() -> None:
    assert "TileDB-Documentation" in note_title("TileDB-Documentation", "2026-05-15")


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


def test_render_group_valid_enml(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_group("2026-05-15", "myrepo", [simple_session])
    assert enml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<!DOCTYPE en-note" in enml
    assert "<en-note>" in enml
    assert enml.rstrip().endswith("</en-note>")


def test_render_group_includes_messages(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_group("2026-05-15", "myrepo", [simple_session])
    assert "Hello, can you help?" in enml
    assert "Of course!" in enml
    assert "Thanks" in enml


def test_render_group_role_labels(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_group("2026-05-15", "myrepo", [simple_session])
    assert "User" in enml
    assert "Assistant" in enml


def test_render_group_session_header_metadata(renderer: Renderer, simple_session: Session) -> None:
    enml = renderer.render_group("2026-05-15", "myrepo", [simple_session])
    assert "/Users/bubba/Documents/git/myrepo" in enml
    assert "main" in enml
    assert "1.0.108" in enml
    assert "messages: 3" in enml.lower()


def test_render_group_escapes_html_in_messages(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "<script>alert('xss')</script>", 10)])
    enml = renderer.render_group("2026-05-15", "x", [s])
    assert "<script>" not in enml
    assert "&lt;script&gt;" in enml


def test_render_group_multiple_sessions_in_time_order(renderer: Renderer) -> None:
    s1 = _session("first", "/x", [_msg("user", "first session", 9)])
    s2 = _session("second", "/x", [_msg("user", "second session", 14)])
    enml = renderer.render_group("2026-05-15", "x", [s1, s2])
    assert enml.index("first session") < enml.index("second session")


def test_render_group_includes_date_header(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "hi", 10)])
    enml = renderer.render_group("2026-05-15", "myrepo", [s])
    assert "2026-05-15" in enml
    assert "myrepo" in enml


def test_render_group_preserves_newlines(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "line one\n\nline two", 10)])
    enml = renderer.render_group("2026-05-15", "x", [s])
    assert "line one" in enml
    assert "line two" in enml
    assert "<br" in enml or "<p" in enml


def test_render_group_empty_list_returns_valid_enml(renderer: Renderer) -> None:
    enml = renderer.render_group("2026-05-15", "empty", [])
    assert "<en-note>" in enml
    assert "</en-note>" in enml


def test_render_email_html_no_enml_wrapper(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_email_html("2026-05-15", "myrepo", [simple_session])
    assert "<?xml" not in html
    assert "<en-note>" not in html
    assert "<h1>" in html


def test_render_email_html_includes_content(renderer: Renderer, simple_session: Session) -> None:
    html = renderer.render_email_html("2026-05-15", "myrepo", [simple_session])
    assert "Hello, can you help?" in html
    assert "myrepo" in html


def test_render_new_messages_includes_update_marker_utc(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "old", 9), _msg("assistant", "new", 14)])
    now = datetime(2026, 5, 15, 14, 30, tzinfo=UTC)
    html = renderer.render_new_messages_html([(s, [s.messages[1]])], now=now)
    assert "Update at 14:30 UTC" in html
    assert "new" in html
    assert "old" not in html


def test_render_new_messages_skips_sessions_with_no_new(renderer: Renderer) -> None:
    s1 = _session("s1", "/x", [_msg("user", "alpha", 9)])
    s2 = _session("s2", "/x", [_msg("user", "beta", 10)])
    now = datetime(2026, 5, 15, 11, 0, tzinfo=UTC)
    html = renderer.render_new_messages_html([(s1, []), (s2, s2.messages)], now=now)
    assert "alpha" not in html
    assert "beta" in html


def test_render_new_messages_includes_session_header(renderer: Renderer) -> None:
    s = _session("s1", "/x/myrepo", [_msg("user", "hi", 10)])
    now = datetime(2026, 5, 15, 11, 0, tzinfo=UTC)
    html = renderer.render_new_messages_html([(s, s.messages)], now=now)
    assert "/x/myrepo" in html


def test_render_new_messages_default_now(renderer: Renderer) -> None:
    s = _session("s1", "/x", [_msg("user", "hi", 10)])
    html = renderer.render_new_messages_html([(s, s.messages)])
    assert "Update at" in html


def test_update_marker_uses_configured_timezone() -> None:
    """When timezone=America/Los_Angeles, the Update at marker shows local time + PDT/PST."""
    renderer = Renderer(timezone=LA)
    s = _session("s1", "/x", [_msg("user", "hi", 10)])
    now = datetime(2026, 5, 15, 14, 30, tzinfo=UTC)  # 07:30 PDT
    html = renderer.render_new_messages_html([(s, s.messages)], now=now)
    assert "Update at 07:30 PDT" in html
    assert "UTC" not in html.split("Update at")[1].split("</")[0]


def test_message_timestamp_uses_configured_timezone() -> None:
    renderer = Renderer(timezone=LA)
    s = _session("s", "/x", [_msg("user", "hi", 18)])  # 18:00 UTC = 11:00 PDT
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "11:00:00 PDT" in html


def test_session_header_uses_configured_timezone() -> None:
    renderer = Renderer(timezone=LA)
    s = _session(
        "s",
        "/x",
        [_msg("user", "hi", 17), _msg("assistant", "bye", 18)],
    )  # 10:00-11:00 PDT
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "10:00-11:00 PDT" in html


def test_utc_renderer_unchanged_format() -> None:
    """Backward compat: a UTC renderer still produces the same UTC labels."""
    renderer = Renderer()  # default UTC
    s = _session("s", "/x", [_msg("user", "hi", 14)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "14:00:00 UTC" in html


def test_render_converts_bold_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "This is **bold** text.", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<strong>bold</strong>" in html
    assert "**bold**" not in html


def test_render_converts_italic_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "An *italic* phrase.", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<em>italic</em>" in html


def test_render_converts_inline_code_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "Use `foo()` to call.", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<code>foo()</code>" in html


def test_render_converts_heading_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "## My Heading\n\nsome text", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<h2>My Heading</h2>" in html


def test_render_converts_link_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "See [the docs](https://example.com).", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert '<a href="https://example.com">the docs</a>' in html


def test_render_converts_bullet_list_markdown(renderer: Renderer) -> None:
    s = _session("s", "/x", [_msg("user", "Items:\n\n- one\n- two\n- three", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<ul>" in html
    assert "<li>one</li>" in html


def test_render_preserves_single_newlines_as_br(renderer: Renderer) -> None:
    """A single \\n between lines should render as <br/>, not collapse to a space."""
    s = _session("s", "/x", [_msg("assistant", "line one\nline two", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<br" in html
    assert "line one" in html and "line two" in html


def test_render_still_escapes_html_tags(renderer: Renderer) -> None:
    """Raw HTML in user text must remain entity-escaped to avoid injection."""
    s = _session("s", "/x", [_msg("user", "Look: <script>alert(1)</script>", 10)])
    html = renderer.render_email_html("2026-05-15", "x", [s])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
