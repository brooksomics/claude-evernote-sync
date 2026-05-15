"""Tests for credentials loading."""

import json
from pathlib import Path

import pytest

from claude_evernote_sync.credentials import GmailCredentials, load_credentials


def test_load_credentials_from_nested(tmp_path: Path) -> None:
    p = tmp_path / "creds.json"
    p.write_text(
        json.dumps(
            {
                "gmail": {
                    "sender": "you@gmail.com",
                    "app_password": "abcd efgh ijkl mnop",
                    "evernote_email": "username.foo@m.evernote.com",
                }
            }
        )
    )
    creds = load_credentials(p)
    assert creds.sender == "you@gmail.com"
    assert creds.app_password == "abcd efgh ijkl mnop"
    assert creds.evernote_email == "username.foo@m.evernote.com"


def test_load_credentials_from_flat(tmp_path: Path) -> None:
    p = tmp_path / "creds.json"
    p.write_text(
        json.dumps(
            {
                "sender": "x@gmail.com",
                "app_password": "p",
                "evernote_email": "y@m.evernote.com",
            }
        )
    )
    creds = load_credentials(p)
    assert creds.sender == "x@gmail.com"


def test_load_credentials_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_credentials(tmp_path / "nope.json")


def test_gmail_credentials_frozen() -> None:
    from dataclasses import FrozenInstanceError

    creds = GmailCredentials(sender="a", app_password="b", evernote_email="c")
    with pytest.raises(FrozenInstanceError):
        creds.sender = "x"  # type: ignore[misc]
