#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCODE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
CLAUDE_DIR="$HOME/.claude"

usage() {
  cat <<EOF
Usage: $(basename "$0") [target] [--uninstall]

Targets:
  opencode     Skills, agents and commands for opencode (default)
  claude       Skills, agents and commands for Claude Code
  all          Both of the above

Options:
  --uninstall  Remove only the symlinks that point into this repo
  -h, --help   Show this help

Locations:
  opencode     ${OPENCODE_DIR}/{skills,agents,commands}
  Claude Code  ${CLAUDE_DIR}/{skills,agents,commands}
EOF
}

link_entries() {
  local src_dir="$1" dest_dir="$2" pattern="${3:-*}"
  [ -d "$src_dir" ] || return 0
  mkdir -p "$dest_dir"
  local item name target
  for item in "$src_dir"/$pattern; do
    [ -e "$item" ] || continue
    name="$(basename "$item")"
    [ "$name" = ".gitkeep" ] && continue
    target="$dest_dir/$name"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$item" ]; then
      echo "  ok       $target"
    elif [ -e "$target" ] && [ ! -L "$target" ]; then
      echo "  SKIP     $target already exists and is not a symlink" >&2
    else
      ln -sfn "$item" "$target"
      echo "  link     $target -> $item"
    fi
  done
}

unlink_entries() {
  local src_dir="$1" dest_dir="$2" pattern="${3:-*}"
  [ -d "$src_dir" ] || return 0
  local item name target
  for item in "$src_dir"/$pattern; do
    [ -e "$item" ] || continue
    name="$(basename "$item")"
    target="$dest_dir/$name"
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$item" ]; then
      rm -f "$target"
      echo "  unlink   $target"
    fi
  done
}

link_skills()   { link_entries   "$REPO_DIR/skills"   "$1/skills"; }
link_agents()   { link_entries   "$REPO_DIR/agents"   "$1/agents" "*.md"; }
link_commands() { link_entries   "$REPO_DIR/commands" "$1/commands" "*.md"; }
unlink_skills()   { unlink_entries "$REPO_DIR/skills"   "$1/skills"; }
unlink_agents()   { unlink_entries "$REPO_DIR/agents"   "$1/agents" "*.md"; }
unlink_commands() { unlink_entries "$REPO_DIR/commands" "$1/commands" "*.md"; }

apply_full_harness() {
  local name="$1" dest="$2"
  echo "${name} -> ${dest}"
  if [ "$UNINSTALL" -eq 1 ]; then
    unlink_skills "$dest"
    unlink_agents "$dest"
    unlink_commands "$dest"
  else
    link_skills "$dest"
    link_agents "$dest"
    link_commands "$dest"
  fi
}

TARGET="opencode"
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    opencode|claude|all) TARGET="$arg" ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; usage; exit 1 ;;
  esac
done

case "$TARGET" in
  opencode) apply_full_harness "OpenCode" "$OPENCODE_DIR" ;;
  claude) apply_full_harness "Claude Code" "$CLAUDE_DIR" ;;
  all)
    apply_full_harness "OpenCode" "$OPENCODE_DIR"
    apply_full_harness "Claude Code" "$CLAUDE_DIR"
    if [ "$UNINSTALL" -eq 0 ]; then
      echo
      echo "Note: opencode reads skills from all installed locations. If you"
      echo "install several harnesses, keep skill names distinct or install"
      echo "only the harnesses you actually use."
    fi
    ;;
esac

if [ "$UNINSTALL" -eq 0 ]; then
  echo
  echo "Done. Restart your agent to pick up the changes."
fi
