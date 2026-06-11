# Contributing

Thanks for taking a look. PRs welcome — please keep them focused and small.

## Dev setup

```bash
git clone https://github.com/brooksomics/claude-evernote-sync.git
cd claude-evernote-sync
uv sync
pre-commit install   # installs the git hook so checks run on every commit
```

## Run the checks

```bash
uv run pytest                   # tests + coverage report (must be >= 80%)
uv run ruff check src/ tests/   # lint
uv run ruff format src/ tests/  # format
uv run mypy src/                # strict type-check
pre-commit run --all-files      # runs all pre-commit hooks against the whole tree
```

CI runs all of the above on every push and pull request. PRs that don't pass CI won't be merged.

One hook (`beads-leak-scan`) guards the maintainer's [beads](https://github.com/gastownhall/beads)
issue tracker data; it skips automatically when `bd` isn't installed, so contributors don't need
beads to commit.

## Coding style

Enforced in CI; the relevant settings live in `pyproject.toml`:

| Constraint | Limit |
|---|---|
| Lines per function | 20 |
| Parameters per function | 3 |
| Nesting depth | 2 |
| Lines per file | 200 |
| Functions per file | 10 |
| Test coverage | 80% (branch coverage) |
| Line length | 100 |
| Python | 3.13+ |

If you bump a limit because the existing one no longer fits, say so in the PR description — usually it means the file/function should be split.

## Tests

Follow RED-GREEN-VALIDATE:

1. **RED** — write a failing test first that captures the desired behavior
2. **GREEN** — minimum code to make it pass
3. **VALIDATE** — run `pre-commit run --all-files && uv run pytest`

Tests should fail first to prove they actually exercise the requirement.

## Commits

- Use the imperative mood (`Add X`, `Fix Y`, not `Added X`)
- One logical change per commit
- Subject line ≤ 72 chars
- Body wraps at 100, explains *why* not *what* (the diff shows the what)

## Reporting bugs

Open an issue with:
- What you tried (`claude-evernote-sync --dry-run -v` output is gold)
- What you expected
- What happened
- Your Evernote plan + macOS version

For security issues, see [SECURITY.md](./SECURITY.md).
