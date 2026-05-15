"""Load Gmail SMTP credentials for sending email-to-Evernote."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CREDENTIALS_PATH = Path("~/.claude-evernote-sync/credentials.json").expanduser()


@dataclass(frozen=True)
class GmailCredentials:
    sender: str
    app_password: str
    evernote_email: str


def _from_dict(raw: dict[str, object]) -> GmailCredentials:
    gmail = raw.get("gmail") if isinstance(raw.get("gmail"), dict) else raw
    assert isinstance(gmail, dict)
    return GmailCredentials(
        sender=str(gmail["sender"]),
        app_password=str(gmail["app_password"]),
        evernote_email=str(gmail["evernote_email"]),
    )


def load_credentials(path: Path = DEFAULT_CREDENTIALS_PATH) -> GmailCredentials:
    """Load Gmail credentials from a chmod-600 JSON file. See credentials.json.example."""
    if not path.exists():
        raise FileNotFoundError(f"Credentials not found at {path}. See README for setup.")
    return _from_dict(json.loads(path.read_text()))
