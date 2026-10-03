#!/usr/bin/env python3
"""Compute the next release tag of main; the CI ``release`` job runs it.

The next tag bumps the newest ``MAJOR.MINOR.PATCH`` tag: ``MINOR`` by
default, ``PATCH`` when a commit subject since that tag contains
``[patch]`` (any case). With no release yet, the first one is ``0.1.0``.
Prints nothing when a release tag already contains HEAD, so a re-run of
the job publishes nothing twice and an older commit whose CI finished after
a newer one is not released.

    python3 scripts/next_release.py                    # print the next tag
    python3 scripts/next_release.py --notes notes.md   # and write release notes

Unlike the installer, a git failure here is an error: CI must stop rather
than publish a wrong version.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from installer.versions import RELEASE_TAG_RE, release_key  # noqa: E402  (after sys.path)

PATCH_MARKER = "[patch]"
FIRST_RELEASE = "0.1.0"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", "replace")


def release_tags(lines: str) -> list[str]:
    return [line.strip() for line in lines.splitlines() if RELEASE_TAG_RE.match(line.strip())]


def bump(last: str | None, subjects: list[str]) -> str:
    """Tag that follows ``last`` given the commit subjects since it."""
    if last is None:
        return FIRST_RELEASE
    major, minor, patch = release_key(last)
    if any(PATCH_MARKER in subject.lower() for subject in subjects):
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


def last_release(repo: Path) -> str | None:
    tags = release_tags(git(repo, "tag", "--list"))
    return max(tags, key=release_key) if tags else None


def next_release(repo: Path) -> str | None:
    """Next tag for HEAD, or None when a release already contains HEAD.

    A release that contains HEAD is HEAD's own tag (a re-run of the job) or
    a newer commit's tag (two pushes whose CI finished out of order): either
    way, tagging HEAD would give older code a higher version.
    """
    if release_tags(git(repo, "tag", "--contains", "HEAD")):
        return None
    last = last_release(repo)
    since = f"{last}..HEAD" if last else "HEAD"
    return bump(last, git(repo, "log", "--format=%s", since).splitlines())


def release_notes(repo: Path) -> str:
    """One line per non-merge commit since the last release."""
    last = last_release(repo)
    since = f"{last}..HEAD" if last else "HEAD"
    return git(repo, "log", "--no-merges", "--pretty=- %s (%h)", since)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=SCRIPTS.parent, help="repository (default: this clone)")
    parser.add_argument("--notes", type=Path, help="also write the release notes to this file")
    args = parser.parse_args(argv)
    tag = next_release(args.repo)
    if tag is None:
        return 0
    if args.notes:
        args.notes.write_text(release_notes(args.repo), encoding="utf-8")
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
