"""Tests for scripts/beads_leak_scan.py (dev utility, loaded by path)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "beads_leak_scan.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("beads_leak_scan", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["beads_leak_scan"] = mod  # dataclasses resolve cls.__module__ here
    spec.loader.exec_module(mod)
    return mod


leak_scan = _load()


def _rules(text: str) -> set[str]:
    return {f.rule for f in leak_scan.scan_text("test", text)}


def test_detects_personal_email() -> None:
    assert "email address" in _rules("reach me at bubba.brooks@gmail.com please")


def test_allows_github_noreply_and_example_emails() -> None:
    clean = "owner 8507447+brooksomics@users.noreply.github.com and user@example.com"
    assert _rules(clean) == set()


def test_detects_ssn() -> None:
    assert "US SSN" in _rules("my ssn is 123-45-6789")


def test_detects_gmail_app_password_shape() -> None:
    assert "Gmail app password" in _rules('app password is "abcd efgh ijkl mnop"')


def test_detects_card_length_digit_run() -> None:
    assert "card-length digit run" in _rules("card 4111111111111111 on file")


def test_detects_secret_assignment() -> None:
    assert "secret assignment" in _rules("set developer_token=S=s1:U=abc123fff")
    assert "secret assignment" in _rules('"api_key": "AIzaSyD9x7x7x7x7"')


def test_clean_technical_text_passes() -> None:
    clean = (
        "Evernote suspended developer-token issuance in Jan 2026. "
        "Thrift NoteStore wrapper (token + host); state tracks synced UUIDs. "
        "Session id 0e45c22 closed at 2026-06-11T03:06:21Z, coverage 93%."
    )
    assert _rules(clean) == set()


def test_findings_carry_source_and_excerpt() -> None:
    findings = leak_scan.scan_text("issues.jsonl", "ssn 123-45-6789")
    assert findings[0].source == "issues.jsonl"
    assert "123-45-6789" in findings[0].excerpt


def test_main_file_mode_fails_on_findings(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.txt"
    dirty.write_text("contact emma.brooks@icloud.com")
    assert leak_scan.main([str(dirty)]) == 1


def test_main_file_mode_passes_clean_files(tmp_path: Path) -> None:
    clean = tmp_path / "clean.txt"
    clean.write_text("nothing personal here, just ENML tables")
    assert leak_scan.main([str(clean)]) == 0


def test_live_mode_skips_cleanly_when_bd_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI and external contributors don't have bd; the hook must not block them."""
    monkeypatch.setattr(leak_scan.shutil, "which", lambda _: None)
    assert leak_scan.main([]) == 0
