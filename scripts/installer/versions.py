"""Derive toolkit and item versions from git.

Releases are the CI tags of the form ``YYYY.MM.DD.N``; older tags such as
``v0.1.0`` are ignored. Nothing here raises on a git problem: every
function degrades to ``None``/``unknown`` when git is missing, the folder
is not a repository, a command fails or times out.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

RELEASE_TAG_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d+$")


def release_key(tag: str) -> tuple[int, int, int, int]:
    """Sortable key of a release tag; 2026.10.03.10 sorts after 2026.10.03.9."""
    year, month, day, count = tag.split(".")
    return (int(year), int(month), int(day), int(count))


@dataclass(frozen=True)
class ToolkitVersion:
    tag: str | None      # newest release tag reachable from HEAD
    ahead: int           # commits since that tag
    dirty: bool          # uncommitted changes in the clone
    commit: str | None   # short sha of HEAD

    @property
    def label(self) -> str:
        if self.tag:
            label = self.tag + (f"+{self.ahead}" if self.ahead else "")
        elif self.commit:
            label = f"dev ({self.commit})"
        else:
            return "unknown"
        return label + (" (modified)" if self.dirty else "")


@dataclass(frozen=True)
class ItemVersion:
    release: str | None  # oldest release tag containing `commit`
    commit: str | None   # short sha of the last commit touching the path
    date: str | None     # YYYY-MM-DD of that commit
    subject: str | None  # its subject line
    local_changes: bool  # git status shows changes under the path

    @property
    def label(self) -> str:
        return (self.release or "unreleased") + ("+local" if self.local_changes else "")


_ITEM_VERSIONS: dict[tuple[str, str], ItemVersion] = {}


def toolkit_version(repo: Path) -> ToolkitVersion:
    """Version of the clone itself: newest release tag, commits ahead, dirtiness."""
    commit = _short_sha(repo)
    if commit is None:
        return ToolkitVersion(tag=None, ahead=0, dirty=False, commit=None)
    tag = _newest_release_reachable(repo)
    ahead = 0
    if tag:
        count = _git(repo, "rev-list", "--count", f"{tag}..HEAD")
        if count and count.strip().isdigit():
            ahead = int(count.strip())
    dirty = bool((_git(repo, "status", "--porcelain") or "").strip())
    return ToolkitVersion(tag=tag, ahead=ahead, dirty=dirty, commit=commit)


def item_version(repo: Path, rel_path: str) -> ItemVersion:
    """Version of one item path; memoised per (repo, rel_path).

    ``release`` is the oldest release tag containing the last commit that
    touched the path, so an item changed after the newest release shows
    ``unreleased`` until a release tag includes the change.
    """
    key = (os.fspath(repo), rel_path)
    cached = _ITEM_VERSIONS.get(key)
    if cached is not None:
        return cached
    version = _read_item_version(repo, rel_path)
    _ITEM_VERSIONS[key] = version
    return version


def clear_cache() -> None:
    """Forget memoised item versions (call after a pull or a commit)."""
    _ITEM_VERSIONS.clear()


def latest_remote_release(repo: Path, timeout: float = 3.0) -> str | None:
    """Newest release tag on ``origin``, or None (no remote, no git, no network)."""
    output = _git(repo, "ls-remote", "--tags", "--refs", "origin", timeout=timeout)
    tags = []
    for line in (output or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        tag = parts[1][len("refs/tags/"):]
        if RELEASE_TAG_RE.match(tag):
            tags.append(tag)
    return max(tags, key=release_key) if tags else None


def pull_status(repo: Path) -> tuple[bool, str]:
    """Whether ``git pull --ff-only`` is safe, and why it is not.

    True only on a branch with an upstream, with a clean working tree whose
    upstream is ahead and contains HEAD.
    """
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return False, "Not a git repository; pull the clone yourself."
    branch = branch.strip()
    if not branch or branch == "HEAD":
        return False, "Not on a branch; check out a branch and pull yourself."
    upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}")
    if upstream is None:
        return False, "No upstream branch; set one with git push -u or pull yourself."
    upstream = upstream.strip()
    if (_git(repo, "status", "--porcelain") or "").strip():
        return False, "You have uncommitted changes; run git pull yourself."
    count = _git(repo, "rev-list", "--count", f"HEAD..{upstream}")
    if count is None or not count.strip().isdigit():
        return False, f"Cannot compare with {upstream}; pull in a terminal."
    if int(count.strip()) == 0:
        # D11: the tracking ref is not behind, but the remote tip may be
        # newer (the update notice comes from ls-remote, before any fetch).
        # A read-only ls-remote keeps U useful without surprise fetches; if
        # HEAD is not ahead of its upstream, `git pull --ff-only` is safe.
        ahead = _git(repo, "rev-list", "--count", f"{upstream}..HEAD")
        if ahead is None or not ahead.strip().isdigit():
            return False, f"Cannot compare with {upstream}; pull in a terminal."
        if int(ahead.strip()) == 0:
            remote = _git(repo, "ls-remote", "origin", f"refs/heads/{branch}", timeout=10)
            head = _git(repo, "rev-parse", "HEAD")
            remote_sha = remote.split()[0] if remote and remote.split() else None
            if remote_sha and head and remote_sha != head.strip():
                return True, f"origin/{branch} has new commits; updating is safe."
        return False, f"Already up to date with {upstream}."
    if _git(repo, "merge-base", "--is-ancestor", "HEAD", upstream) is None:
        return False, f"Your branch and {upstream} have diverged; pull yourself."
    return True, f"{upstream} has new commits; updating is safe."


def pull(repo: Path) -> tuple[bool, str]:
    """Run ``git pull --ff-only``; returns (ok, output shown to the user)."""
    output = _git(repo, "pull", "--ff-only", timeout=60)
    if output is None:
        return False, "git pull --ff-only failed; pull in a terminal to see why."
    return True, output.strip() or "Already up to date."


def _short_sha(repo: Path) -> str | None:
    output = _git(repo, "rev-parse", "--short", "HEAD")
    if output is None:
        return None
    return output.strip() or None


def _newest_release_reachable(repo: Path) -> str | None:
    output = _git(repo, "tag", "--merged", "HEAD")
    tags = [line.strip() for line in (output or "").splitlines() if RELEASE_TAG_RE.match(line.strip())]
    return max(tags, key=release_key) if tags else None


def _oldest_release_containing(repo: Path, commit: str) -> str | None:
    output = _git(repo, "tag", "--contains", commit)
    tags = [line.strip() for line in (output or "").splitlines() if RELEASE_TAG_RE.match(line.strip())]
    return min(tags, key=release_key) if tags else None


def _read_item_version(repo: Path, rel_path: str) -> ItemVersion:
    info = _git(repo, "log", "-1", "--format=%h%x00%cs%x00%s", "--", rel_path)
    release = commit = date = subject = None
    if info and info.strip():
        parts = info.split("\x00")
        commit = parts[0].strip() or None
        if len(parts) > 1:
            date = parts[1].strip() or None
        if len(parts) > 2:
            subject = parts[2].strip() or None
        if commit:
            release = _oldest_release_containing(repo, commit)
    local_changes = bool((_git(repo, "status", "--porcelain", "--", rel_path) or "").strip())
    return ItemVersion(
        release=release, commit=commit, date=date, subject=subject, local_changes=local_changes
    )


def _git(repo: Path, *args: str, timeout: float = 10) -> str | None:
    """Run ``git -C <repo> ...``; stdout, or None when git fails in any way."""
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")
