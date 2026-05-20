"""Orchestration + CLI entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from claude_evernote_sync.config import DEFAULT_CONFIG_PATH, DEFAULT_STATE_PATH, Config, load_config
from claude_evernote_sync.credentials import load_credentials
from claude_evernote_sync.destinations import Destination, SyncContext
from claude_evernote_sync.destinations.api import ApiDestination
from claude_evernote_sync.destinations.email import EmailDestination
from claude_evernote_sync.evernote_client import EvernoteSync
from claude_evernote_sync.formatter import Renderer, note_title_for_session, resolve_timezone
from claude_evernote_sync.grouping import bucket_for_cwd
from claude_evernote_sync.parser import Session, parse_jsonl_file
from claude_evernote_sync.state import SyncState, load_state, save_state
from claude_evernote_sync.summary import (
    attach_ai_titles,
    attach_cross_file_summaries,
    extract_ai_title_records,
    extract_summary_records,
)

LOG_PATH = Path("~/.claude-evernote-sync/sync.log").expanduser()
logger = logging.getLogger("claude_evernote_sync")


def discover_jsonl_files(projects_dir: Path, days_back: int) -> list[Path]:
    """Return JSONL files modified within the last `days_back` days."""
    if not projects_dir.exists():
        return []
    cutoff_ts = (datetime.now(UTC) - timedelta(days=days_back)).timestamp()
    return [p for p in projects_dir.rglob("*.jsonl") if p.stat().st_mtime >= cutoff_ts]


def parse_all(paths: list[Path]) -> list[Session]:
    sessions = [parse_jsonl_file(p) for p in paths]
    resolved = [s for s in sessions if s is not None]
    summaries = [r for p in paths for r in extract_summary_records(p)]
    attach_cross_file_summaries(resolved, summaries)
    ai_titles = [r for p in paths for r in extract_ai_title_records(p)]
    attach_ai_titles(resolved, ai_titles)
    return resolved


def make_destination(config: Config) -> Destination:
    """Instantiate the destination selected by `config.backend`."""
    renderer = Renderer(timezone=resolve_timezone(config.display_timezone))
    if config.backend == "email":
        return EmailDestination(creds=load_credentials(), renderer=renderer)
    client = EvernoteSync(config.developer_token, config.api_host)
    return ApiDestination(client=client, renderer=renderer)


@dataclass
class SyncJob:
    """Bundles the mutable run-time dependencies of a sync pass."""

    destination: Destination
    state: SyncState
    config: Config

    def sync_all(self, sessions: list[Session]) -> int:
        count = 0
        for session in sorted(sessions, key=lambda s: s.start_ts):
            if self.config.force:
                self.state.sessions.pop(session.session_id, None)
            ctx = self._make_context(session)
            synced = self.destination.sync_session(ctx)
            if synced:
                self.state.mark_synced(session.session_id, synced, title=ctx.title)
                count += 1
                logger.info("synced: %s (%d new msgs)", ctx.title, len(synced))
        return count

    def _make_context(self, session: Session) -> SyncContext:
        bucket = bucket_for_cwd(session.cwd, self.config.rollup_overrides)
        record = self.state.record_for(session.session_id)
        title = record.title if record else note_title_for_session(session, bucket)
        prefix = self.config.notebook_prefix
        notebook = self.config.notebook_overrides.get(bucket) or (
            f"{prefix}{bucket}" if prefix else self.config.notebook_name
        )
        return SyncContext(
            session=session,
            bucket=bucket,
            title=title,
            synced_uuids=record.synced_uuids if record else set(),
            notebook_name=notebook,
        )


def run(config: Config, dry_run: bool = False) -> int:
    paths = discover_jsonl_files(config.projects_dir, config.days_back)
    logger.info("found %d JSONL files within %d days", len(paths), config.days_back)
    sessions = parse_all(paths)
    if config.limit is not None:
        sessions = sorted(sessions, key=lambda s: s.end_ts, reverse=True)[: max(0, config.limit)]
        logger.info("limit=%d applied — %d sessions selected", config.limit, len(sessions))
    logger.info("parsed %d sessions", len(sessions))
    if dry_run:
        _log_dry_run(sessions, config)
        return 0
    state = load_state(DEFAULT_STATE_PATH)
    job = SyncJob(destination=make_destination(config), state=state, config=config)
    count = job.sync_all(sessions)
    save_state(state, DEFAULT_STATE_PATH)
    return count


def _log_dry_run(sessions: list[Session], config: Config) -> None:
    for session in sorted(sessions, key=lambda s: s.start_ts):
        bucket = bucket_for_cwd(session.cwd, config.rollup_overrides)
        title = note_title_for_session(session, bucket)
        logger.info("[dry-run] would sync: %s (%d msgs)", title, session.message_count)


def _setup_logging(verbose: bool) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_PATH), logging.StreamHandler()]
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="claude-evernote-sync")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    p.add_argument("--dry-run", action="store_true", help="Show what would be synced")
    p.add_argument("--days", type=int, help="Override config days_back")
    p.add_argument("--limit", type=int, help="Sync at most N most-recently-active sessions")
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-send all messages for matched sessions; clears their state first",
    )
    p.add_argument("--backfill", action="store_true", help="Sync all history")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def cli(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(args.verbose)
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 2
    if args.backfill:
        config.days_back = 365 * 10
    elif args.days is not None:
        config.days_back = args.days
    if args.limit is not None:
        config.limit = args.limit
    if args.force:
        config.force = True
    run(config, dry_run=args.dry_run)
    return 0
