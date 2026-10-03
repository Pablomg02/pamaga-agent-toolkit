#!/usr/bin/env bash
# Legacy-friendly entry point. It keeps the old arguments and delegates to
# scripts/install.py: with no arguments in an interactive terminal it opens
# the installer TUI, and any other use maps to the non-interactive CLI.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PAMAGA_PYTHON:-python3}"
OPENCODE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
CLAUDE_DIR="$HOME/.claude"
ANTIGRAVITY_DIR="$HOME/.gemini/config"

usage() {
  cat <<EOF
Usage: $(basename "$0") [target] [--uninstall]

Targets:
  opencode     Skills, agents and command wrappers for opencode (default)
  claude       Skills and agents for Claude Code (skills are already /commands)
  antigravity  Skills for Antigravity CLI (skills are already /commands)
  all          All of the above

Options:
  --uninstall  Remove only the symlinks and copies installed by this toolkit
  -h, --help   Show this help

Locations:
  opencode       ${OPENCODE_DIR}/{skills,agents,commands}
  Claude Code    ${CLAUDE_DIR}/{skills,agents}
  Antigravity    ${ANTIGRAVITY_DIR}/skills
EOF
}

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: python3 is required by the installer; install Python 3.9+ and retry" >&2
  exit 1
fi

TARGET="opencode"
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    opencode|claude|antigravity|all) TARGET="$arg" ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 1 ;;
  esac
done

# No arguments in an interactive terminal: the friendly full-screen installer.
if [ "$#" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then
  exec "$PYTHON" "$REPO_DIR/scripts/install.py"
fi

case "$TARGET" in
  opencode) HARNESSES="opencode" ;;
  claude) HARNESSES="claude" ;;
  antigravity) HARNESSES="antigravity" ;;
  all) HARNESSES="opencode,claude,antigravity" ;;
esac

if [ "$UNINSTALL" -eq 1 ]; then
  exec "$PYTHON" "$REPO_DIR/scripts/install.py" --uninstall --harness "$HARNESSES" --offline
fi

exec "$PYTHON" "$REPO_DIR/scripts/install.py" --yes --harness "$HARNESSES" \
  --skills all --offline
