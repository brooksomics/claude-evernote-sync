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
from claude_evernote_sync.formatter import Renderer, note_title, resolve_timezone
from claude_evernote_sync.grouping import GroupKey, group_sessions
from claude_evernote_sync.parser import Session, parse_jsonl_file
from claude_evernote_sync.state import SyncState, load_state, save_state

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
    return [s for s in sessions if s is not None]


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

    def sync_all(self, groups: dict[GroupKey, list[Session]]) -> int:
        count = 0
        for key, sessions in sorted(groups.items()):
            ctx = self._make_context(key, sessions)
            synced = self.destination.sync_group(ctx)
            if synced:
                self.state.mark_synced(key, synced)
                count += 1
                logger.info("synced: %s (%d new msgs)", note_title(key[1], key[0]), len(synced))
        return count

    def _make_context(self, key: GroupKey, sessions: list[Session]) -> SyncContext:
        notebook = self.config.notebook_overrides.get(key[1], self.config.notebook_name)
        return SyncContext(
            date_iso=key[0],
            bucket=key[1],
            sessions=sessions,
            synced_uuids=self.state.synced_for(key),
            notebook_name=notebook,
        )


def run(config: Config, dry_run: bool = False) -> int:
    paths = discover_jsonl_files(config.projects_dir, config.days_back)
    logger.info("found %d JSONL files within %d days", len(paths), config.days_back)
    sessions = parse_all(paths)
    groups = group_sessions(sessions, config.rollup_overrides)
    logger.info("parsed %d sessions into %d groups", len(sessions), len(groups))
    if dry_run:
        _log_dry_run(groups)
        return 0
    state = load_state(DEFAULT_STATE_PATH)
    job = SyncJob(destination=make_destination(config), state=state, config=config)
    count = job.sync_all(groups)
    save_state(state, DEFAULT_STATE_PATH)
    return count


def _log_dry_run(groups: dict[GroupKey, list[Session]]) -> None:
    for (date_iso, bucket), sessions in sorted(groups.items()):
        title = note_title(bucket, date_iso)
        logger.info("[dry-run] would sync: %s (%d sessions)", title, len(sessions))


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
    run(config, dry_run=args.dry_run)
    return 0
