#!/usr/bin/env python3
"""Coordinate several agents working on the same repository.

Each agent works on its own branch in its own git worktree and leaves a short
note on a board that every worktree can see: .git/agent-work/<slug>.md.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

BOARD = "agent-work"
BRANCH_PREFIX = "work/"
STALE_AFTER = datetime.timedelta(hours=2)
STATUSES = ("working", "finished")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GLOB_CHARS = set("*?[")
FIELDS = ("task", "status", "branch", "worktree", "base", "paths", "expect", "progress", "started", "updated")


class WorkError(Exception):
    """A user-facing error: printed without a traceback, exit code 1."""


# --- git and board helpers ---------------------------------------------------


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise WorkError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def repo_paths(cwd: Path) -> tuple[Path, Path]:
    """Return (main worktree root, board folder) for the repository at cwd."""
    common = Path(git("rev-parse", "--git-common-dir", cwd=cwd))
    if not common.is_absolute():
        common = (cwd / common).resolve()
    if common.name != ".git":
        raise WorkError("bare repositories are not supported")
    return common.parent, common / BOARD


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def parse_time(text: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def read_note(path: Path) -> dict[str, str]:
    note = {"slug": path.stem}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            if key.strip() in FIELDS:
                note[key.strip()] = value.strip()
    return note


def write_note(path: Path, note: dict[str, str], exclusive: bool = False) -> None:
    text = "".join(f"{key}: {note.get(key, '')}\n" for key in FIELDS)
    # "x" fails if another agent created the same note first.
    with path.open("x" if exclusive else "w", encoding="utf-8") as handle:
        handle.write(text)


def notes(board: Path) -> list[dict[str, str]]:
    if not board.is_dir():
        return []
    return [read_note(p) for p in sorted(board.glob("*.md"))]


def note_path(board: Path, slug: str) -> Path:
    path = board / f"{slug}.md"
    if not path.is_file():
        raise WorkError(f"no note for {slug!r} on the board")
    return path


def is_stale(note: dict[str, str], at: datetime.datetime) -> bool:
    updated = parse_time(note.get("updated", ""))
    return note.get("status") == "working" and (updated is None or at - updated > STALE_AFTER)


def age(note: dict[str, str], at: datetime.datetime) -> str:
    updated = parse_time(note.get("updated", ""))
    if updated is None:
        return "unknown"
    minutes = int((at - updated).total_seconds() // 60)
    return f"{minutes} min ago" if minutes < 120 else f"{minutes // 60} h ago"


def split_paths(text: str) -> list[str]:
    return [p.strip().strip("/") for p in text.split(",") if p.strip()]


def fixed_parts(pattern: str) -> list[str]:
    """Path components before the first one containing a glob character."""
    parts = []
    for part in pattern.split("/"):
        if GLOB_CHARS & set(part):
            break
        parts.append(part)
    return parts


def overlaps(a: str, b: str) -> bool:
    """Conservative check: could patterns a and b match a common file?"""
    pa, pb = fixed_parts(a), fixed_parts(b)
    shorter = min(len(pa), len(pb))
    return pa[:shorter] == pb[:shorter]


def conflicts(mine: list[str], others: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    found = []
    for note in others:
        if note.get("status") != "working":
            continue
        for theirs in split_paths(note.get("paths", "")):
            for path in mine:
                if overlaps(path, theirs):
                    found.append((note["slug"], path, theirs))
    return found


# --- commands ----------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    _, board = repo_paths(Path.cwd())
    at = now()
    entries = notes(board)
    if not entries:
        print("board is empty: no other agent is working on this repository")
        return 0
    for note in entries:
        status = note.get("status", "?")
        if is_stale(note, at):
            status += ", STALE (no ping for over 2 h)"
        print(f"{note['slug']}  [{status}]  last ping {age(note, at)}")
        for key in ("task", "branch", "worktree", "paths", "expect", "progress"):
            if note.get(key):
                print(f"    {key}: {note[key]}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    if not SLUG_RE.match(args.slug):
        raise WorkError(f"invalid slug {args.slug!r}: use lowercase words joined by hyphens")
    main_root, board = repo_paths(Path.cwd())
    paths = split_paths(args.paths)
    if not paths:
        raise WorkError("--paths needs at least one path or glob, e.g. 'src/auth/**,docs/auth.md'")

    clashes = conflicts(paths, notes(board))
    if clashes and not args.allow_overlap:
        print("overlap with work in progress:")
        for slug, mine, theirs in clashes:
            print(f"  {mine}  vs  {theirs}  ({slug})")
        print("nothing created; ask the user, then retry with --allow-overlap if they agree")
        return 2

    base = args.base or git("rev-parse", "--abbrev-ref", "HEAD", cwd=main_root)
    if base == "HEAD":
        raise WorkError(
            f"{main_root} is not on a branch (detached HEAD), so there is nothing to "
            "merge back into; pass --base <branch>"
        )
    branch = BRANCH_PREFIX + args.slug
    worktree = main_root.parent / f"{main_root.name}-work" / args.slug
    stamp = now().isoformat()
    note = {
        "task": args.task,
        "status": "working",
        "branch": branch,
        "worktree": str(worktree),
        "base": base,
        "paths": ", ".join(paths),
        "expect": args.expect or "-",
        "progress": "started",
        "started": stamp,
        "updated": stamp,
    }
    board.mkdir(exist_ok=True)
    path = board / f"{args.slug}.md"
    try:
        write_note(path, note, exclusive=True)
    except FileExistsError:
        raise WorkError(f"{args.slug!r} is already on the board; pick another slug") from None
    try:
        git("worktree", "add", "-b", branch, str(worktree), note["base"], cwd=main_root)
    except WorkError:
        path.unlink()
        raise
    print(f"started {args.slug}: branch {branch}")
    print(f"work in: {worktree}")
    return 0


def cmd_ping(args: argparse.Namespace) -> int:
    _, board = repo_paths(Path.cwd())
    path = note_path(board, args.slug)
    note = read_note(path)
    note["updated"] = now().isoformat()
    if args.status:
        note["status"] = args.status
    if args.progress:
        note["progress"] = args.progress
    write_note(path, note)
    print(f"{args.slug}: {note['status']}, {note.get('progress', '')}")
    return 0


def cmd_end(args: argparse.Namespace) -> int:
    main_root, board = repo_paths(Path.cwd())
    path = note_path(board, args.slug)
    note = read_note(path)
    worktree = Path(note.get("worktree", ""))
    if note.get("worktree") and worktree.exists():
        if Path.cwd().resolve().is_relative_to(worktree.resolve()):
            raise WorkError(f"run this from outside {worktree}, e.g. from {main_root}")
        remove = ["worktree", "remove", str(worktree)] + (["--force"] if args.force else [])
        try:
            git(*remove, cwd=main_root)
        except WorkError as error:
            raise WorkError(f"{error}\nthe worktree has uncommitted changes; commit them, or use --force to discard") from None
        print(f"removed worktree {worktree}")
        if worktree.parent.is_dir() and not any(worktree.parent.iterdir()):
            worktree.parent.rmdir()  # the <repo>-work folder, once the last worktree is gone
    branch = note.get("branch", "")
    if branch:
        delete = ["branch", "-D" if args.force else "-d", branch]
        try:
            git(*delete, cwd=main_root)
            print(f"deleted branch {branch}")
        except WorkError:
            print(f"kept branch {branch}: it is not merged into {note.get('base') or 'its base'}")
    path.unlink()
    print(f"removed {args.slug} from the board")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show who is working on what").set_defaults(func=cmd_list)

    p = sub.add_parser("start", help="add your note, create your branch and worktree")
    p.add_argument("slug", help="short name for the work, e.g. fix-export")
    p.add_argument("--task", required=True, help="one line: what you are doing")
    p.add_argument("--paths", required=True, help="comma-separated paths or globs you will modify")
    p.add_argument("--expect", help="one line: what others should expect, e.g. 'login() signature changes'")
    p.add_argument("--base", help="branch to start from (default: the main worktree's current branch)")
    p.add_argument("--allow-overlap", action="store_true", help="start even if paths overlap (user agreed)")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("ping", help="signal you are alive; optionally update status or progress")
    p.add_argument("slug")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--progress", help="one line: where you are")
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("end", help="remove your note, worktree, and branch if merged")
    p.add_argument("slug")
    p.add_argument("--force", action="store_true", help="discard uncommitted changes and unmerged branch")
    p.set_defaults(func=cmd_end)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except WorkError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
