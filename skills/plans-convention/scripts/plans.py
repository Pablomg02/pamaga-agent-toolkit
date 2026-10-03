#!/usr/bin/env python3
"""Manage plan folders following the plans-convention skill.

Plans live in <repo>/plans/{backlog,in-progress,done}/<id>-<slug>/plan.md.
The folder a plan sits in is its status; ids are global and never reused.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import NamedTuple

STATUSES = ("backlog", "in-progress", "done")
TYPES = ("plan", "roadmap", "ticket")
PLAN_FILE = "plan.md"
PAGE_FILE = "plan.html"
ID_WIDTH = 4
SLUG_MAX = 48

FOLDER_RE = re.compile(r"^(\d{%d,})-([a-z0-9]+(?:-[a-z0-9]+)*)$" % ID_WIDTH)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PAGE_META_RE = re.compile(
    r'<meta\s+name="plan-source-sha256"\s+content="([0-9a-f]*)"\s*/?>', re.IGNORECASE
)
# Anything that makes the page load a resource from outside the file itself.
EXTERNAL_RE = re.compile(
    r"""<script[^>]+\bsrc\s*=|<link[^>]+\bhref\s*=|<iframe\b|"""
    r"""\b(?:src|srcset|poster|data)\s*=\s*["']?\s*(?!data:|#)[^"'\s>]+|"""
    r"""@import\b|url\(\s*["']?\s*(?!data:|#)""",
    re.IGNORECASE,
)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class PlanError(Exception):
    """A user-facing error: printed without a traceback, exit code 1."""


class Entry(NamedTuple):
    number: int
    slug: str
    status: str
    path: Path

    @property
    def id(self) -> str:
        return format_id(self.number)


# --- helpers -----------------------------------------------------------------


def format_id(number: int) -> str:
    return str(number).zfill(ID_WIDTH)


def parse_id(text: str) -> int:
    text = text.strip()
    if not text.isdigit():
        raise PlanError(f"invalid id {text!r}: expected digits, e.g. 0042 or 42")
    return int(text)


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(slug) > SLUG_MAX:
        slug = slug[:SLUG_MAX].rsplit("-", 1)[0] or slug[:SLUG_MAX]
    return slug.strip("-")


def find_plans_dir(start: Path) -> Path:
    """Walk up from start to the first folder holding plans/ or .git."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / "plans").is_dir() or (folder / ".git").exists():
            return folder / "plans"
    return start / "plans"


def read_frontmatter(plan_md: Path) -> dict[str, str]:
    """Parse the flat `key: value` frontmatter used by plan.md files."""
    try:
        lines = plan_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        quoted = re.match(r"""^(["'])(.*?)(?<!\\)\1""", value)
        if quoted:
            value = quoted.group(2).replace('\\"', '"').replace("\\\\", "\\")
        else:
            value = value.split(" #", 1)[0].strip()
        data[key.strip()] = value
    return {}  # unterminated frontmatter


def scan(plans_dir: Path) -> tuple[list[Entry], list[str]]:
    """Return the plan folders found and a list of layout problems."""
    entries: list[Entry] = []
    problems: list[str] = []
    for status in STATUSES:
        status_dir = plans_dir / status
        if not status_dir.is_dir():
            continue
        for child in sorted(status_dir.iterdir()):
            if child.name.startswith(".") or not child.is_dir():
                if not child.name.startswith("."):
                    problems.append(f"{child}: unexpected file in a status folder")
                continue
            match = FOLDER_RE.match(child.name)
            if not match:
                problems.append(
                    f"{child}: folder name must be <id>-<slug>, "
                    f"e.g. {format_id(7)}-add-login"
                )
                continue
            entries.append(Entry(int(match.group(1)), match.group(2), status, child))
    return entries, problems


def resolve(plans_dir: Path, ref: str) -> Entry:
    """Find a plan by id ("42", "0042") or by the path of its folder."""
    entries, _ = scan(plans_dir)
    candidate = Path(ref)
    if candidate.is_dir():
        target = candidate.resolve()
        for entry in entries:
            if entry.path.resolve() == target:
                return entry
        raise PlanError(f"{ref} is not a plan folder under {plans_dir}")
    number = parse_id(ref)
    matches = [e for e in entries if e.number == number]
    if not matches:
        raise PlanError(f"no plan with id {format_id(number)} in {plans_dir}")
    if len(matches) > 1:
        paths = ", ".join(str(m.path) for m in matches)
        raise PlanError(f"id {format_id(number)} is duplicated: {paths}")
    return matches[0]


def git_lines(cwd: Path, *args: str) -> list[str]:
    """Output lines of a git command, or [] if git is missing or fails."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError:
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def ids_elsewhere(plans_dir: Path) -> dict[int, list[str]]:
    """Ids used in other git worktrees and local branches, with where.

    Two agents on different branches or worktrees would otherwise both pick
    the same next id and collide at merge time.
    """
    root = plans_dir.resolve().parent
    if not root.is_dir():
        return {}
    top = git_lines(root, "rev-parse", "--show-toplevel")
    if not top:
        return {}
    toplevel = Path(top[0]).resolve()
    try:
        rel = plans_dir.resolve().relative_to(toplevel)
    except ValueError:
        return {}

    found: dict[int, list[str]] = {}
    for line in git_lines(root, "worktree", "list", "--porcelain"):
        if not line.startswith("worktree "):
            continue
        other = Path(line[len("worktree "):]).resolve()
        if other != toplevel:
            for entry in scan(other / rel)[0]:
                found.setdefault(entry.number, []).append(f"worktree {other}")
    status_paths = [f"{rel.as_posix()}/{status}/" for status in STATUSES]
    for branch in git_lines(root, "for-each-ref", "--format=%(refname:short)", "refs/heads"):
        for path in git_lines(root, "ls-tree", "-d", "--name-only", branch, "--", *status_paths):
            match = FOLDER_RE.match(path.rsplit("/", 1)[-1])
            if match:
                found.setdefault(int(match.group(1)), []).append(f"branch {branch}")
    return found


def next_number(entries: list[Entry], elsewhere: dict[int, list[str]]) -> int:
    used = [e.number for e in entries] + list(elsewhere)
    return max(used, default=0) + 1


def page_status(folder: Path) -> str:
    """'missing', 'fresh' or 'stale' for the generated page of a plan folder."""
    page, plan_md = folder / PAGE_FILE, folder / PLAN_FILE
    if not page.is_file():
        return "missing"
    match = PAGE_META_RE.search(page.read_text(encoding="utf-8"))
    if not match or not plan_md.is_file():
        return "stale"
    return "fresh" if match.group(1) == sha256(plan_md) else "stale"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- commands ----------------------------------------------------------------


def cmd_next_id(plans_dir: Path, args: argparse.Namespace) -> int:
    entries, _ = scan(plans_dir)
    print(format_id(next_number(entries, ids_elsewhere(plans_dir))))
    return 0


def cmd_check_id(plans_dir: Path, args: argparse.Namespace) -> int:
    number = parse_id(args.id)
    entries, _ = scan(plans_dir)
    used = [str(e.path) for e in entries if e.number == number]
    used += ids_elsewhere(plans_dir).get(number, [])
    if used:
        for where in used:
            print(f"used: {where}")
        return 1
    print(f"free: {format_id(number)}")
    return 0


def cmd_new(plans_dir: Path, args: argparse.Namespace) -> int:
    slug = args.slug or slugify(args.title)
    if not slug or not SLUG_RE.match(slug):
        raise PlanError(f"invalid slug {slug!r}: use lowercase words joined by hyphens")
    entries, _ = scan(plans_dir)
    parent_line = ""
    if args.parent:
        parent = resolve(plans_dir, args.parent)
        parent_type = read_frontmatter(parent.path / PLAN_FILE).get("type")
        if parent_type != "roadmap":
            raise PlanError(f"parent {parent.id} is a {parent_type or 'unknown type'}, not a roadmap")
        parent_line = f'parent: "{parent.id}"\n'

    number = next_number(entries, ids_elsewhere(plans_dir))
    folder = plans_dir / "backlog" / f"{format_id(number)}-{slug}"
    template = (TEMPLATES_DIR / f"{args.type}.md").read_text(encoding="utf-8")
    title = args.title.replace("\\", "\\\\").replace('"', '\\"')
    content = (
        template.replace("{{id}}", format_id(number))
        .replace("{{title_yaml}}", title)
        .replace("{{title}}", args.title)
        .replace("{{date}}", datetime.date.today().isoformat())
        .replace("{{parent_line}}", parent_line)
    )
    folder.mkdir(parents=True)
    (folder / PLAN_FILE).write_text(content, encoding="utf-8")
    print(folder)
    return 0


def cmd_find(plans_dir: Path, args: argparse.Namespace) -> int:
    print(resolve(plans_dir, args.ref).path)
    return 0


def cmd_move(plans_dir: Path, args: argparse.Namespace) -> int:
    entry = resolve(plans_dir, args.ref)
    if entry.status == args.status:
        print(entry.path)
        return 0
    target = plans_dir / args.status / entry.path.name
    if target.exists():
        raise PlanError(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    entry.path.rename(target)
    print(target)
    return 0


def cmd_list(plans_dir: Path, args: argparse.Namespace) -> int:
    entries, _ = scan(plans_dir)
    rows = []
    for entry in sorted(entries, key=lambda e: e.number):
        meta = read_frontmatter(entry.path / PLAN_FILE)
        kind = meta.get("type", "?")
        if args.status and entry.status != args.status:
            continue
        if args.type and kind != args.type:
            continue
        title = meta.get("title", entry.slug)
        parent = f" (parent {meta['parent']})" if meta.get("parent") else ""
        rows.append(f"{entry.id}  {entry.status:<11}  {kind:<7}  {title}{parent}")
    print("\n".join(rows) if rows else "no plans found")
    return 0


def cmd_validate(plans_dir: Path, args: argparse.Namespace) -> int:
    if not plans_dir.is_dir():
        print(f"no plans folder at {plans_dir}")
        return 0
    entries, errors = scan(plans_dir)
    warnings: list[str] = []
    allowed_top = set(STATUSES) | {"README.md"}
    for child in plans_dir.iterdir():
        if child.name not in allowed_top and not child.name.startswith("."):
            errors.append(f"{child}: only {', '.join(STATUSES)} and README.md belong in plans/")

    by_number: dict[int, list[Entry]] = {}
    for entry in entries:
        by_number.setdefault(entry.number, []).append(entry)
    for number, group in sorted(by_number.items()):
        if len(group) > 1:
            paths = ", ".join(str(e.path) for e in group)
            errors.append(f"id {format_id(number)} is used by several folders: {paths}")

    for entry in entries:
        plan_md = entry.path / PLAN_FILE
        if not plan_md.is_file():
            errors.append(f"{entry.path}: missing {PLAN_FILE}")
            continue
        meta = read_frontmatter(plan_md)
        if not meta:
            errors.append(f"{plan_md}: missing or unterminated frontmatter")
            continue
        if meta.get("id") != entry.id:
            errors.append(f"{plan_md}: frontmatter id {meta.get('id')!r} != folder id {entry.id!r}")
        if meta.get("type") not in TYPES:
            errors.append(f"{plan_md}: type must be one of {', '.join(TYPES)}")
        if not meta.get("title"):
            errors.append(f"{plan_md}: missing title")
        parent = meta.get("parent")
        if parent:
            parents = by_number.get(int(parent)) if parent.isdigit() else None
            if not parents:
                errors.append(f"{plan_md}: parent {parent} does not exist")
            elif read_frontmatter(parents[0].path / PLAN_FILE).get("type") != "roadmap":
                errors.append(f"{plan_md}: parent {parent} is not a roadmap")
        if page_status(entry.path) == "stale":
            warnings.append(f"{entry.path / PAGE_FILE}: out of date with {PLAN_FILE}")

    for message in errors:
        print(f"error: {message}")
    for message in warnings:
        print(f"warning: {message}")
    if not errors:
        print(f"ok: {len(entries)} plan folder(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_page_status(plans_dir: Path, args: argparse.Namespace) -> int:
    print(page_status(resolve(plans_dir, args.ref).path))
    return 0


def cmd_stamp_page(plans_dir: Path, args: argparse.Namespace) -> int:
    entry = resolve(plans_dir, args.ref)
    page = entry.path / PAGE_FILE
    if not page.is_file():
        raise PlanError(f"{page} does not exist; write the page first")
    html = page.read_text(encoding="utf-8")
    meta = f'<meta name="plan-source-sha256" content="{sha256(entry.path / PLAN_FILE)}">'
    if PAGE_META_RE.search(html):
        html = PAGE_META_RE.sub(meta, html, count=1)
    else:
        head = re.search(r"<head[^>]*>", html, re.IGNORECASE)
        if not head:
            raise PlanError(f"{page} has no <head> element")
        html = html[: head.end()] + "\n" + meta + html[head.end() :]
    page.write_text(html, encoding="utf-8")

    external = sorted({m.group(0).strip() for m in EXTERNAL_RE.finditer(html)})
    if external:
        print(f"stamped {page}, but it is not self-contained:")
        for snippet in external:
            print(f"  external reference: {snippet}")
        return 1
    print(f"stamped {page}")
    return 0


# --- entry point -------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--plans-dir",
        type=Path,
        help="plans folder to use (default: plans/ at the repository root)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("next-id", help="print the next free id").set_defaults(func=cmd_next_id)

    p = sub.add_parser("check-id", help="exit 0 if an id is free, 1 if it is used")
    p.add_argument("id")
    p.set_defaults(func=cmd_check_id)

    p = sub.add_parser("new", help="create a plan folder in backlog/ from a template and print its path")
    p.add_argument("--title", required=True)
    p.add_argument("--type", choices=TYPES, default="plan")
    p.add_argument("--slug", help="default: derived from the title")
    p.add_argument("--parent", help="id of the roadmap this plan derives from")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("find", help="print the folder of a plan")
    p.add_argument("ref", help="plan id or folder path")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("move", help="move a plan folder to another status")
    p.add_argument("ref", help="plan id or folder path")
    p.add_argument("status", choices=STATUSES)
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("list", help="list plan folders")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--type", choices=TYPES)
    p.set_defaults(func=cmd_list)

    sub.add_parser("validate", help="check layout, ids and frontmatter").set_defaults(
        func=cmd_validate
    )

    p = sub.add_parser("page-status", help=f"print missing, fresh or stale for {PAGE_FILE}")
    p.add_argument("ref", help="plan id or folder path")
    p.set_defaults(func=cmd_page_status)

    p = sub.add_parser("stamp-page", help=f"record the {PLAN_FILE} hash in {PAGE_FILE}")
    p.add_argument("ref", help="plan id or folder path")
    p.set_defaults(func=cmd_stamp_page)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plans_dir = args.plans_dir or find_plans_dir(Path.cwd())
    try:
        return args.func(plans_dir, args)
    except PlanError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
