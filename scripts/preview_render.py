#!/usr/bin/env python3
"""Preview how recent real sessions render, by emailing them to Evernote.

A developer utility (not imported by the package). It renders your most-recent
sessions with the current formatter + config and sends them as clearly labeled
"PREVIEW" notes, WITHOUT touching sync_state — so it never interferes with the
normal hourly sync. Handy for eyeballing formatting changes against real
conversations before they sync for real.

    uv run python scripts/preview_render.py        # 1 most-recent session
    uv run python scripts/preview_render.py 5      # N most-recent sessions

Reads ~/.claude-evernote-sync/{config.toml,credentials.json} like the real CLI.
Delete the resulting PREVIEW notes afterwards.
"""

from __future__ import annotations

import sys

from claude_evernote_sync.config import Config, load_config
from claude_evernote_sync.credentials import load_credentials
from claude_evernote_sync.email_client import EmailNote, send
from claude_evernote_sync.formatter import Renderer, note_title_for_session, resolve_timezone
from claude_evernote_sync.grouping import bucket_for_cwd
from claude_evernote_sync.main import discover_jsonl_files, parse_all
from claude_evernote_sync.parser import Session


def _recent_sessions(config: Config, count: int) -> list[Session]:
    sessions = parse_all(discover_jsonl_files(config.projects_dir, config.days_back))
    return sorted(sessions, key=lambda s: s.end_ts, reverse=True)[:count]


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    config = load_config()
    creds = load_credentials()
    renderer = Renderer(
        timezone=resolve_timezone(config.display_timezone),
        content_depth=config.content_depth,
    )
    sessions = _recent_sessions(config, count)
    if not sessions:
        print(f"No sessions in the last {config.days_back} days (see scan.days_back).")
        return
    for session in sessions:
        bucket = bucket_for_cwd(session.cwd, config.rollup_overrides)
        title = f"PREVIEW (new format): {note_title_for_session(session, bucket)}"
        send(creds, EmailNote(title=title, html_body=renderer.render_session_html(session)))
        print(f"sent: {title}")
    print(f"\nSent {len(sessions)} preview note(s) to {creds.evernote_email}.")


if __name__ == "__main__":
    main()
