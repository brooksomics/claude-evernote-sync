# CLAUDE.md

Project instructions for Claude Code working in this repo. Keep it short and pointed; details live in README/CONTRIBUTING/SECURITY.

## What this is

A Python CLI + hourly launchd job that mirrors Claude Code session JSONL files (`~/.claude/projects/`) into Evernote as daily rollup notes per git repo.

Two backends behind a pluggable `Destination` Protocol:
- **`email`** (default, works today): SMTP via Gmail to Evernote's email-to-note address. Append-only — uses per-session synced-UUID state to avoid resending; each session is a separate Evernote note with a title locked at first sync.
- **`api`** (currently blocked): Evernote NoteStore REST. Code is ready but Evernote suspended new developer-token issuance in Jan 2026. Don't delete this code; it's the fast path once they reopen access.

A future `mcp` destination is anticipated (Evernote announced an MCP integration without a timeline).

## Tech stack

- Python 3.13+ managed with [`uv`](https://github.com/astral-sh/uv)
- `evernote-plus` (Python 3 fork of the official SDK) for the api backend
- `smtplib` (stdlib) for the email backend
- Tests: `pytest` + `pytest-cov` with branch coverage
- Lint/format: `ruff`. Types: `mypy --strict`. Secrets: `gitleaks`.

## Run the checks

```bash
uv run pytest                   # full suite + coverage (must be >= 80%)
uv run ruff check src/ tests/   # lint
uv run ruff format src/ tests/  # format in place
uv run mypy src/                # strict type-check
pre-commit run --all-files      # everything pre-commit runs on every commit
uv run claude-evernote-sync --dry-run -v   # exercise without sending email
```

After cloning, always `pre-commit install` so the git hook is active.

## Code conventions (enforced — not aspirational)

These limits are checked in CI; bumping a limit usually means the file or function should be split:

| Limit | Value |
|---|---|
| Lines per function | 20 |
| Parameters per function | 3 |
| Nesting depth | 2 |
| Lines per file | 200 |
| Functions per file | 10 |
| Branch coverage | ≥ 80% |
| Line length | 100 |

Other rules:
- **TDD: RED → GREEN → VALIDATE.** Write a failing test first; make it pass with minimum code; then run the full check suite. Bug fixes start with a failing test that reproduces the bug.
- No new dependencies without a real reason. Stdlib first.
- No defensive programming for cases that can't happen. Trust framework/internal guarantees. Validate only at boundaries (config load, JSONL parse, SMTP errors).
- No mocked tests for code that talks to disk or an external service when an integration test would do — except for SMTP and the Evernote API, which we mock because we can't hit them in CI.
- Don't add backward-compat shims, deprecated aliases, or `# removed:` placeholder comments. Delete things cleanly.
- Avoid comments that restate the code. Comments are for *why* (non-obvious constraints, workaround for a specific bug), not *what*.

## Architecture cheat sheet

```
parser.py       JSONL → Session (dataclass) with messages + metadata + optional summary
summary.py      Extract type=summary JSONL records; cross-file match by leafUuid
grouping.py     bucket_for_cwd — derive the rollup bucket name from a session's cwd
formatter.py    Render one session to ENML (api) or HTML email body (email);
                note_title_for_session locks a title from summary / first prompt
state.py        Persistent {session_id: SessionRecord{synced_uuids, title}}
credentials.py  Load Gmail/Evernote credentials from chmod-600 JSON
email_client.py SMTP_SSL send with Evernote subject syntax
evernote_client.py  Thrift NoteStore wrapper (token + host)
destinations/
  __init__.py   SyncContext (per-session) + Destination Protocol
  email.py      EmailDestination — uses state, append-only, per-session subject
  api.py        ApiDestination  — idempotent upsert, lazy notebook cache
main.py         CLI + orchestration. SyncJob bundles dest+state+config.
```

When adding a new destination, implement the `Destination` protocol (one method: `sync_session(ctx: SyncContext) -> set[str]`) and add a branch in `main.make_destination`. Don't try to make all destinations look the same beyond that interface — email is fundamentally append-only with a locked subject, the api is idempotent upsert keyed on title, and a future MCP backend will have its own constraints.

## Commit style

Use Conventional Commits:

```
<type>: <short summary in imperative mood>

<optional body explaining why>

<optional footer with Co-Authored-By, refs, etc.>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `style`.

Examples:
- `feat: add notebook_overrides for per-bucket routing`
- `fix: prevent duplicate notes when state is reset`
- `docs: clarify email-to-note notebook fallback behavior`
- `refactor: bundle destination + state + config into SyncJob`

Subject ≤ 72 chars. Body wraps at 100. Explain *why*, not *what* (the diff is the what). Sign-off line for AI-assisted commits is fine and welcome.

## Never commit

Pre-commit blocks these, but as a backup: if you ever see any of these staged, stop and investigate.

- `config.toml` (real user config — may contain a developer_token)
- `credentials.json` (Gmail app password + Evernote email)
- `sync_state.json` (synced UUIDs — not secret but pollutes diffs)
- Anything matching `*.log`
- Any file with a high-entropy string that looks token-like (gitleaks will catch it, but be aware)

The `*.example` versions (`config.toml.example`, `credentials.json.example`) are the templates and *do* live in the repo. They contain only placeholder values.

## Branch model

`main` is **branch-protected** — direct pushes are rejected. Every change goes through a feature branch and a pull request, including the maintainer's own work.

### Workflow for any agent (Claude Code or otherwise) working in this repo

1. **Branch from `origin/main`, not local `main`** (local main may be divergent if a previous run was interrupted):

   ```bash
   git fetch origin
   git checkout -b <type>/<short-name> origin/main
   ```

2. **Branch name prefixes** (Conventional Commits–aligned):
   - `fix/` — bug fixes
   - `feat/` — new functionality
   - `docs/` — documentation only
   - `refactor/`, `test/`, `chore/`, `ci/`, `perf/` — as needed

3. **Commit normally** with a Conventional Commit message (see [Commit style](#commit-style) above).

4. **Push the branch and surface the PR URL** to the user:

   ```bash
   git push -u origin <branch>
   # GitHub prints a "Create a pull request" URL — hand that to the user
   ```

5. **Do not push to `main` directly.** The push will be rejected, and you'll leave the local branch divergent (1 commit ahead of `origin/main`). Cleanup requires `git reset --hard origin/main`, which is destructive and needs explicit user approval.

6. **After a PR merges**, the user reconciles local `main` themselves:

   ```bash
   git checkout main && git fetch && git reset --hard origin/main
   ```

   Don't try to do this on the user's behalf without their go-ahead.

### One PR per concern

Don't bundle unrelated changes onto a single feature branch. A typo fix and a new feature get two PRs, not one. CI runs against each PR independently, and small PRs review faster.

### External contributors

Same workflow. CI must be green (lint + format + mypy + pytest + pre-commit + gitleaks) before merge.

## Cross-reference

- [README.md](./README.md) — user-facing docs, setup, CLI reference
- [CONTRIBUTING.md](./CONTRIBUTING.md) — human contributor onboarding
- [SECURITY.md](./SECURITY.md) — threat model + how to report vulns


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
