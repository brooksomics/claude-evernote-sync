#!/usr/bin/env bash
# Leak-scan beads data, then push it to the Dolt remote.
#
# `bd dolt push` bypasses git hooks, so this wrapper is the only place a
# scan can run before issue text reaches GitHub. Use it instead of calling
# `bd dolt push` directly.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

uv run python scripts/beads_leak_scan.py
bd dolt push "$@"
