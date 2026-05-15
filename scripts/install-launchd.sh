#!/usr/bin/env bash
# Install the launchd agent for hourly Claude Code -> Evernote sync.
# Idempotent: re-run after changes to update.

set -euo pipefail

REPO_PATH="$(cd "$(dirname "$0")/.." && pwd)"
HOME_PATH="$HOME"
LABEL="com.claudeevernote.sync"
TEMPLATE="${REPO_PATH}/launchd/claude-evernote-sync.plist.template"
INSTALL_PATH="${HOME_PATH}/Library/LaunchAgents/${LABEL}.plist"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "error: template not found at $TEMPLATE" >&2
    exit 1
fi

UV_PATH="$(command -v uv || true)"
if [[ -z "$UV_PATH" ]]; then
    echo "error: 'uv' not found in PATH. Install from https://github.com/astral-sh/uv" >&2
    exit 1
fi

if launchctl list "$LABEL" >/dev/null 2>&1; then
    echo "Unloading existing agent..."
    launchctl unload "$INSTALL_PATH" 2>/dev/null || true
fi

mkdir -p "${HOME_PATH}/.claude-evernote-sync"
mkdir -p "${HOME_PATH}/Library/LaunchAgents"

sed \
    -e "s|__UV_PATH__|${UV_PATH}|g" \
    -e "s|__REPO_PATH__|${REPO_PATH}|g" \
    -e "s|__HOME__|${HOME_PATH}|g" \
    "$TEMPLATE" > "$INSTALL_PATH"

launchctl load "$INSTALL_PATH"

echo "Installed: $INSTALL_PATH"
echo "Logs: ~/.claude-evernote-sync/launchd.out.log"
echo "Force a run with: launchctl start $LABEL"
echo "Uninstall with:   launchctl unload $INSTALL_PATH && rm $INSTALL_PATH"
