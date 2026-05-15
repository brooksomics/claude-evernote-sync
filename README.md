# claude-evernote-sync

[![CI](https://github.com/brooksomics/claude-evernote-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/brooksomics/claude-evernote-sync/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python: 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

Automatically sync [Claude Code](https://claude.com/claude-code) CLI conversations to Evernote as daily rollup notes, grouped by project.

Each git repo gets one note per day. A four-hour conversation lands in **one** note that grows hourly — not four separate notes.

## Why this exists

Claude Code stores every conversation as a JSONL file under `~/.claude/projects/`, but there's no built-in way to archive them outside that directory. If you want to keep a searchable record of what you've worked on, you're stuck copy-pasting transcripts into your knowledge base. This tool automates that for Evernote users.

## Backends

Pick one in `config.toml`:

| Backend | Status | What it does |
|---|---|---|
| `email` (default) | **Works today** | Uses Evernote's [email-to-note](https://help.evernote.com/hc/en-us/articles/209005347-Save-emails-into-Evernote) feature. Requires a Gmail account + app password. Append-only — each hourly run sends only new messages. |
| `api` | **Blocked** | Uses Evernote's NoteStore API. Evernote [suspended new developer-token issuance](https://discussion.evernote.com/forums/topic/156356-api-key-requests-suspended/) in Jan 2026. Code is ready; activate when EN reopens access. |
| `mcp` | **Future** | Evernote has announced an upcoming [MCP integration](https://evernote.com/mcp). Will be added here when it ships. |

## Quick start (email backend)

### Prerequisites

- macOS (other Unix-likes should work but launchd is Mac-specific)
- Python 3.13+ and [`uv`](https://github.com/astral-sh/uv)
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords)
- An Evernote account on any plan (Free, Starter, or Advanced) — the [email-to-note](https://help.evernote.com/hc/en-us/articles/209005347-Save-emails-into-Evernote) feature works on all of them

### 1. Clone + install

```bash
git clone https://github.com/<you>/claude-evernote-sync.git
cd claude-evernote-sync
uv sync
```

### 2. Find your Evernote email-to-note address

In Evernote: **Account → Account Info → Email Notes to**. It looks like `username.xxx@m.evernote.com`. Treat it like a password — anyone who has it can email content into your account.

### 2a. Create the destination notebook(s) in Evernote

Before your first sync, manually create the notebook you'll use (default: `claude_convos`) by clicking **New Notebook** in Evernote. If you configure `[notebook_overrides]` later for per-bucket routing, create those notebooks too.

This step matters because Evernote's email-to-note feature **silently falls back to your default notebook** if the `@notebook` reference doesn't exist or has a typo — notes won't be lost, but they'll land in the wrong place and you'll have to move them manually. The `api` backend creates notebooks automatically; the `email` backend cannot.

### 3. Configure

```bash
mkdir -p ~/.claude-evernote-sync
cp config.toml.example ~/.claude-evernote-sync/config.toml
cp credentials.json.example ~/.claude-evernote-sync/credentials.json
chmod 600 ~/.claude-evernote-sync/credentials.json
```

Edit `~/.claude-evernote-sync/credentials.json` and fill in your Gmail sender, app password, and Evernote email address.

### 4. Dry-run

Confirm what would be synced without touching Evernote:

```bash
uv run claude-evernote-sync --dry-run -v
```

You should see lines like:

```
found 44 JSONL files within 2 days
parsed 44 sessions into 16 groups
[dry-run] would sync: Claude Sessions — myrepo — 2026-05-15 (3 sessions)
```

If the buckets look right, proceed.

### 5. First real sync

```bash
uv run claude-evernote-sync -v             # last 2 days
uv run claude-evernote-sync --backfill -v  # everything (initial bulk import)
```

### 6. Schedule hourly via launchd

```bash
./scripts/install-launchd.sh
```

This script installs a `com.claudeevernote.sync` LaunchAgent that runs the sync hourly. It substitutes your local paths into a template — no hardcoded usernames.

Useful commands:

```bash
launchctl start com.claudeevernote.sync     # force a run now
launchctl list | grep claudeevernote        # check status
launchctl unload ~/Library/LaunchAgents/com.claudeevernote.sync.plist
rm ~/Library/LaunchAgents/com.claudeevernote.sync.plist  # uninstall
```

## What gets synced

For each Claude Code session JSONL:

- **Included**: user prompts, assistant text responses, session metadata (project path, git branch, version, message count)
- **Excluded**: tool calls (Bash, Read, Edit, etc.), tool results, thinking blocks, fenced code blocks

Sessions are grouped by `(start-date, bucket)` where `bucket` is:

1. The configured override path's basename if `cwd` is under one (see `rollup_overrides`)
2. Else, the git repo root's basename
3. Else, the immediate directory's basename

## Configuration reference

See [`config.toml.example`](./config.toml.example) for all options. Key fields:

```toml
[evernote]
backend = "email"               # "email" or "api"
notebook_name = "claude_convos" # default destination notebook
developer_token = ""            # required for backend = "api"

[scan]
projects_dir = "~/.claude/projects"
days_back = 2

[grouping]
rollup_overrides = ["/path/to/workspace"]  # absorb child repos

[notebook_overrides]
# "tile-ai" = "TileAI Notes"   # route specific buckets to their own notebooks
# biotech_jobs = "Job Search"
```

### Per-bucket notebook routing

By default everything lands in `claude_convos`. Use `[notebook_overrides]` to route specific buckets to different notebooks — useful if some projects should live alongside other notes for that area of work.

Keys are bucket names (= git repo root's basename, or `rollup_overrides` path basename). Values are the target notebook name. Anything not listed falls back to `notebook_name`.

**Important:** with the `email` backend you must create each referenced notebook in Evernote manually before first sync. Email-to-note's `@notebook` syntax silently routes to your default notebook if the target doesn't exist. The `api` backend auto-creates notebooks.

## CLI reference

```
claude-evernote-sync [--config PATH] [--dry-run] [--days N] [--backfill] [-v]
```

| Flag | Default | Effect |
|---|---|---|
| `--config PATH` | `~/.claude-evernote-sync/config.toml` | Config file location |
| `--dry-run` | off | Print what would be synced; no Evernote calls |
| `--days N` | from config | Override `days_back` for this run |
| `--backfill` | off | Sync everything (sets `days_back=3650`) |
| `-v` | off | Verbose logging |

## How the "growing note" pattern works (email backend)

State lives in `~/.claude-evernote-sync/sync_state.json` — a per-group set of message UUIDs that have already been emailed. Each hourly run:

1. Walks all Claude Code sessions started in the last `days_back` days
2. Groups them by `(start-date, bucket)`
3. For each group, finds messages whose UUIDs aren't in state
4. If the group has never been synced: sends a **create** email (`Subject @Notebook`) with the full content so far
5. Otherwise: sends an **append** email (`Subject @Notebook +`) with only the new messages
6. Marks those UUIDs as synced

Evernote's email-to-note rule for append: a `+` at the end of the subject line tells Evernote to append the body to the most recent note matching the title before the `+`. So note titles are deterministic and don't change between runs.

### State file size

The state file (`sync_state.json`) grows by roughly:

| Use level | Messages/year | Growth/year |
|---|---|---|
| Light (~50 msgs/day) | ~18k | ~1 MB |
| Heavy (~500 msgs/day) | ~180k | ~9 MB |

A decade of heavy use lands around 90 MB — well under any practical concern, and parse time stays sub-second on modern SSDs.

**The state file is safe to delete at any time**, but be aware of one caveat: after deletion, the next sync will treat every `(date, bucket)` group as a first sync and send `CREATE` emails. If matching notes already exist in Evernote (because they were synced previously), email-to-note will create **duplicate notes** alongside them rather than appending. To avoid duplicates after a state reset:

- Delete the affected notes in Evernote before re-syncing, OR
- Limit the re-sync to brand-new content with `--days 1` so old groups aren't touched

There is no automatic pruning. If state growth ever becomes an actual problem, you can `rm ~/.claude-evernote-sync/sync_state.json` and accept the duplicate-note tradeoff for any re-synced historical groups.

## Files written

- `~/.claude-evernote-sync/config.toml` — your config (no secrets)
- `~/.claude-evernote-sync/credentials.json` — Gmail + Evernote email (chmod 600; **gitignored**)
- `~/.claude-evernote-sync/sync_state.json` — synced UUIDs per group
- `~/.claude-evernote-sync/sync.log` — application log
- `~/.claude-evernote-sync/launchd.out.log` — launchd stdout
- `~/.claude-evernote-sync/launchd.err.log` — launchd stderr

## Privacy / data flow

For the `email` backend:

1. Your script reads JSONL files from `~/.claude/projects/`
2. Formats messages locally on your Mac
3. Sends via SMTP to `smtp.gmail.com:465` (Gmail handles delivery to Evernote)
4. Evernote receives the email, files it under the specified notebook

Your conversations transit Gmail's servers en route to Evernote. If you'd rather avoid that, the `api` backend (when unblocked) sends directly to Evernote without an SMTP middleman.

## Troubleshooting

**`Config not found`** — Copy `config.toml.example` to `~/.claude-evernote-sync/config.toml`.

**`Credentials not found`** — Copy `credentials.json.example` to `~/.claude-evernote-sync/credentials.json` and fill it in. Don't forget `chmod 600`.

**`SMTPAuthenticationError`** — Wrong Gmail app password. Generate a new one at https://myaccount.google.com/apppasswords (you'll need 2FA enabled on the Google account).

**Email arrives but no note appears in Evernote** — Check that the sender address matches what Evernote has on file for your account. Email-to-note rejects from unknown senders.

**Notes land in my default notebook instead of `claude_convos`** — The target notebook doesn't exist (or there's a typo). Create the notebook in Evernote manually, then move the stray notes into it. Future syncs will land correctly.

**Notes don't append, new ones get created instead** — The append `+` syntax requires an exact title match. Don't manually rename the auto-generated notes. Also: a note that's currently open in the Evernote app is locked against email updates; close it and retry.

**`backend='api' requires evernote.developer_token`** — You've selected the `api` backend in config but haven't pasted a developer token. Evernote API requests are currently suspended (Jan 2026 onward); use `backend = "email"` instead.

## Roadmap

- **MCP backend** when [Evernote's MCP](https://evernote.com/mcp) ships
- **Direct API backend** auto-enabled if Evernote reopens developer-token issuance

## Development

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full setup. Quick version:

```bash
git clone https://github.com/brooksomics/claude-evernote-sync.git
cd claude-evernote-sync
uv sync
pre-commit install               # installs the git hook
uv run pytest                    # full suite, coverage report
```

Quality gates enforced by CI:
- 20 lines per function (max)
- 3 params per function (max)
- 2 nesting levels (max)
- 200 lines per file (max)
- 10 functions per file (max)
- 80% branch coverage (min)
- Strict mypy + ruff lint + ruff format

Secret scanning via `gitleaks` runs on every commit and CI build.

## Security

See [SECURITY.md](./SECURITY.md) for the threat model and how to report a vulnerability.

## License

MIT. See [LICENSE](./LICENSE).
