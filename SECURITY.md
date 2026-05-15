# Security Policy

## Reporting a vulnerability

If you find a security issue in `claude-evernote-sync`, please **do not open a public GitHub issue**.

Instead, email the maintainer directly with details, or open a private security advisory via GitHub:
https://github.com/brooksomics/claude-evernote-sync/security/advisories/new

I'll acknowledge within a few days and discuss disclosure timing.

## What this tool touches

When you run `claude-evernote-sync`, it:

- **Reads** every `.jsonl` file under `~/.claude/projects/` modified within `days_back` days. Those files contain your full Claude Code conversation history — prompts, assistant responses, tool calls, file edits, command outputs.
- **Writes** sync state to `~/.claude-evernote-sync/sync_state.json` (list of synced message UUIDs only — no content).
- **Reads** credentials from `~/.claude-evernote-sync/credentials.json` (Gmail app password + Evernote email address; create with `chmod 600`).
- **Sends** filtered conversation content (user prompts + assistant text, with tool calls and code blocks stripped) over SMTP to `smtp.gmail.com:465`, addressed to your Evernote secret email.

Nothing is sent to any third party except Gmail (en route) and Evernote (destination). No telemetry, no analytics.

## Secret handling

| File | Should be on disk? | In git? |
|---|---|---|
| `~/.claude-evernote-sync/credentials.json` | yes (chmod 600) | **no** (gitignored) |
| `~/.claude-evernote-sync/config.toml` | yes | **no** (gitignored, may contain a developer token if you use the api backend) |
| `config.toml.example` / `credentials.json.example` | repo only | yes (placeholders only) |

The repo enforces this with:
- `.gitignore` excluding all runtime state files
- A `pre-commit` hook (`forbid-local-state`) that hard-fails if any of those paths are staged
- `gitleaks` scanning the diff on every commit and every CI run for high-entropy secrets

If you accidentally commit a real credential, **rotate it immediately** (revoke the Gmail app password, regenerate the Evernote email-to-note address) before worrying about git history rewrites — by the time you've noticed, the value is effectively public.

## Threat model (briefly)

- **Local attacker (read access to your home dir)**: can read your credentials.json and impersonate the email-to-note flow. Mitigation: `chmod 600`, FileVault on macOS.
- **Mass scan of public GitHub for `m.evernote.com` strings**: if your `credentials.json` leaks via git, attackers can flood your Evernote with notes. Mitigation: gitignore + gitleaks + the `forbid-local-state` pre-commit hook.
- **Gmail account compromise**: if your Gmail app password leaks, attackers can send arbitrary email from your address. Mitigation: store only an app-password (revocable independently of your main password); rotate periodically.
- **MITM between you and smtp.gmail.com**: not possible — `SMTP_SSL` enforces TLS to Gmail; Gmail enforces TLS to Evernote.

## Out of scope

- The Evernote NoteStore API client (`destinations/api.py`) is unused right now because Evernote suspended developer-token issuance in January 2026. Vulnerabilities in code that nobody can execute are not a priority.
