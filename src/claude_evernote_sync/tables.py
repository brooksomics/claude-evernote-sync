"""Add Evernote-surviving border styles to markdown-generated tables."""

from __future__ import annotations

import re

# Evernote's email->ENML conversion strips every border except those on
# tables, so a borderless <table> arrives as an invisible grid. Inline
# borders on each cell are what keep the structure legible. The markdown
# `tables` extension emits bare cells, or cells with exactly
# `style="text-align: <dir>;"` for aligned columns — merge, don't clobber.
_CELL = re.compile(r'<(t[hd])(?: style="text-align: (\w+);")?>')
_CELL_STYLE = "border:1px solid #ccc;padding:2px 8px"


def _styled_cell(match: re.Match[str]) -> str:
    tag, align = match.groups()
    style = _CELL_STYLE if align is None else f"{_CELL_STYLE};text-align:{align}"
    return f'<{tag} style="{style}">'


def style_tables(html: str) -> str:
    """Inline border styles onto <table>/<th>/<td> emitted by markdown."""
    html = html.replace("<table>", '<table style="border-collapse:collapse">')
    return _CELL.sub(_styled_cell, html)
