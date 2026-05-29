"""Pins the rendering features the README's "What a note looks like" section
shows off, against the synthetic demo session in fixtures/demo_session.jsonl.

If the formatter changes how it renders roles, code, headings, or tool calls,
these fail — so the documented example can't silently drift out of date.
"""

from pathlib import Path

from claude_evernote_sync.formatter import Renderer, note_title_for_session
from claude_evernote_sync.grouping import bucket_for_cwd
from claude_evernote_sync.main import parse_all

DEMO = Path(__file__).parent / "fixtures" / "demo_session.jsonl"


def _demo_html() -> str:
    sessions = parse_all([DEMO])
    assert len(sessions) == 1
    return Renderer().render_session_html(sessions[0])


def test_demo_renders_colored_role_labels() -> None:
    html = _demo_html()
    assert 'font-weight:bold">You</span>' in html
    assert 'font-weight:bold">Claude</span>' in html


def test_demo_renders_code_block_as_pre() -> None:
    html = _demo_html()
    assert "<pre>" in html
    assert "def mandelbrot(width=80, height=24):" in html


def test_demo_renders_markdown_heading_for_toc() -> None:
    # Assistant ## headings become real <h2>s — Evernote builds its TOC/folding from them.
    assert "<h2>The renderer</h2>" in _demo_html()


def test_demo_renders_compact_tool_calls() -> None:
    html = _demo_html()
    for tool in ("Read", "Write", "Bash", "Task"):
        assert f"<code>{tool}</code>" in html
    assert "Render a 60-wide Mandelbrot to eyeball it" in html  # a Bash call's summary


def test_demo_title_comes_from_ai_title() -> None:
    session = parse_all([DEMO])[0]
    title = note_title_for_session(session, bucket_for_cwd(session.cwd, []))
    assert title.startswith("Add an ASCII Mandelbrot renderer - ")
