"""Load configuration from TOML."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.claude-evernote-sync/config.toml").expanduser()
DEFAULT_STATE_PATH = Path("~/.claude-evernote-sync/sync_state.json").expanduser()
VALID_BACKENDS = {"email", "api"}
VALID_SUBAGENT_MODES = {"keep", "suppress"}
VALID_CONTENT_DEPTHS = {"conversation", "full"}


@dataclass
class Config:
    backend: str = "email"
    notebook_name: str = "claude_convos"
    notebook_prefix: str = ""
    notebook_overrides: dict[str, str] = field(default_factory=dict)
    developer_token: str = ""
    api_host: str = "www.evernote.com"
    projects_dir: Path = field(default_factory=lambda: Path("~/.claude/projects").expanduser())
    days_back: int = 2
    quiet_minutes: int = 15
    rollup_overrides: list[str] = field(default_factory=list)
    display_timezone: str = "UTC"
    limit: int | None = None
    force: bool = False
    subagent_notes: str = "keep"
    content_depth: str = "full"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load config from TOML. Raises FileNotFoundError if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Config not found at {path}. See config.toml.example.")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    config = _from_raw(raw)
    _validate(config)
    return config


def _from_raw(raw: dict[str, object]) -> Config:
    ev = _section(raw, "evernote")
    scan = _section(raw, "scan")
    render = _section(raw, "render")
    raw_rollup = _section(raw, "grouping").get("rollup_overrides", [])
    rollup = [str(x) for x in raw_rollup] if isinstance(raw_rollup, list) else []
    return Config(
        backend=str(ev.get("backend", "email")),
        notebook_name=str(ev.get("notebook_name", "claude_convos")),
        notebook_prefix=str(ev.get("notebook_prefix", "")),
        notebook_overrides=_str_map(raw.get("notebook_overrides")),
        developer_token=str(ev.get("developer_token", "")),
        api_host=str(ev.get("api_host", "www.evernote.com")),
        projects_dir=Path(str(scan.get("projects_dir", "~/.claude/projects"))).expanduser(),
        days_back=int(scan.get("days_back", 2)),  # type: ignore[call-overload]
        quiet_minutes=int(scan.get("quiet_minutes", 15)),  # type: ignore[call-overload]
        rollup_overrides=rollup,
        display_timezone=str(_section(raw, "display").get("timezone", "UTC")),
        subagent_notes=str(render.get("subagent_notes", "keep")),
        content_depth=str(render.get("content_depth", "full")),
    )


def _str_map(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _validate(config: Config) -> None:
    if config.backend not in VALID_BACKENDS:
        raise ValueError(f"Invalid backend: {config.backend!r}. Must be one of {VALID_BACKENDS}.")
    if config.backend == "api" and not config.developer_token:
        raise ValueError("backend='api' requires evernote.developer_token in config.toml.")
    if config.subagent_notes not in VALID_SUBAGENT_MODES:
        raise ValueError(
            f"Invalid render.subagent_notes: {config.subagent_notes!r}. "
            f"Must be one of {VALID_SUBAGENT_MODES}."
        )
    if config.content_depth not in VALID_CONTENT_DEPTHS:
        raise ValueError(
            f"Invalid render.content_depth: {config.content_depth!r}. "
            f"Must be one of {VALID_CONTENT_DEPTHS}."
        )
    _validate_timezone(config.display_timezone)


def _validate_timezone(tz_str: str) -> None:
    from claude_evernote_sync.formatter import resolve_timezone

    try:
        resolve_timezone(tz_str)
    except Exception as e:
        raise ValueError(f"Invalid display.timezone {tz_str!r}: {e}") from e


def _section(raw: dict[str, object], name: str) -> dict[str, object]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        return {}
    return value
