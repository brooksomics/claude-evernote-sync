"""SMTP client for Evernote's email-to-note feature.

Subject syntax (Evernote-controlled):
    <Title> [@notebook] [#tag] [!reminder] [+]

The trailing "+" appends the email body to the most recent note matching <Title>.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from claude_evernote_sync.credentials import GmailCredentials

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


@dataclass(frozen=True)
class EmailNote:
    title: str
    html_body: str
    append: bool = False
    notebook: str | None = None


def build_subject(note: EmailNote) -> str:
    """Construct the Evernote-flavored subject line."""
    parts = [note.title]
    if note.notebook:
        parts.append(f"@{note.notebook}")
    if note.append:
        parts.append("+")
    return " ".join(parts)


def _build_mime(creds: GmailCredentials, note: EmailNote) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = build_subject(note)
    msg["From"] = creds.sender
    msg["To"] = creds.evernote_email
    msg.attach(MIMEText(note.html_body, "html"))
    return msg


def send(creds: GmailCredentials, note: EmailNote) -> None:
    """Send a single email-to-note. Raises smtplib errors on failure."""
    msg = _build_mime(creds, note)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(creds.sender, creds.app_password)
        server.sendmail(creds.sender, creds.evernote_email, msg.as_string())
    logger.info("emailed: %s (append=%s)", note.title, note.append)
