"""Tests for config loading."""

from pathlib import Path

import pytest

from claude_evernote_sync.config import Config, load_config


def test_load_config_minimal(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[evernote]\nbackend = "email"\n')
    config = load_config(cfg_path)
    assert config.backend == "email"
    assert config.api_host == "www.evernote.com"
    assert config.notebook_name == "claude_convos"
    assert config.days_back == 2


def test_load_config_full(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        "[evernote]\n"
        'backend = "api"\n'
        'developer_token = "tok"\n'
        'api_host = "sandbox.evernote.com"\n'
        'notebook_name = "MyNotebook"\n'
        "[scan]\n"
        'projects_dir = "~/x"\n'
        "days_back = 5\n"
        "[grouping]\n"
        'rollup_overrides = ["/a/b", "/c/d"]\n'
    )
    config = load_config(cfg_path)
    assert config.backend == "api"
    assert config.developer_token == "tok"
    assert config.api_host == "sandbox.evernote.com"
    assert config.notebook_name == "MyNotebook"
    assert config.days_back == 5
    assert config.rollup_overrides == ["/a/b", "/c/d"]


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.toml")


def test_config_defaults() -> None:
    config = Config()
    assert config.backend == "email"
    assert config.developer_token == ""
    assert config.api_host == "www.evernote.com"
    assert config.notebook_name == "claude_convos"
    assert config.days_back == 2
    assert config.rollup_overrides == []


def test_load_config_email_backend_no_token_ok(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[evernote]\nbackend = "email"\n')
    config = load_config(cfg_path)
    assert config.backend == "email"


def test_load_config_api_backend_requires_token(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[evernote]\nbackend = "api"\n')
    with pytest.raises(ValueError, match="developer_token"):
        load_config(cfg_path)


def test_load_config_invalid_backend_rejected(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[evernote]\nbackend = "mcp"\n')
    with pytest.raises(ValueError, match="Invalid backend"):
        load_config(cfg_path)


def test_load_config_notebook_overrides(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[evernote]\nbackend = "email"\n'
        "[notebook_overrides]\n"
        '"tile-ai" = "TileAI Notes"\n'
        'biotech_jobs = "Job Search"\n'
    )
    config = load_config(cfg_path)
    assert config.notebook_overrides == {"tile-ai": "TileAI Notes", "biotech_jobs": "Job Search"}


def test_load_config_no_overrides_section(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[evernote]\nbackend = "email"\n')
    config = load_config(cfg_path)
    assert config.notebook_overrides == {}
