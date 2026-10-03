"""Derive toolkit and item versions from git.

Stable releases are the CI tags of ``main`` with the semver form
``MAJOR.MINOR.PATCH`` (``0.1.0``, ``0.2.0``...). The working branch ``dev``
has no tags and no releases: a dev clone's version is its commit, shown as
``0.2.0+3 (dev)`` when it is three commits past ``0.2.0`` or ``dev (abc1234)``
when no release is reachable. Tags that are not semver (``v0.1.0``) are
ignored. Nothing here raises on a git problem: every function degrades to
``None``/``unknown`` when git is missing, the folder is not a repository, a
command fails or times out.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

RELEASE_TAG_RE = re.compile(r"^\d+\.\d+\.\d+$")
DEV_BRANCH = "dev"


def release_key(tag: str) -> tuple[int, ...]:
    """Sortable key of a release tag; 0.10.0 sorts after 0.9.0."""
    return tuple(int(part) for part in tag.split("."))


@dataclass(frozen=True)
class ToolkitVersion:
    tag: str | None      # newest release tag reachable from HEAD
    ahead: int           # commits since that tag
    dirty: bool          # uncommitted changes in the clone
    commit: str | None   # short sha of HEAD
    dev: bool = False    # the clone follows the development channel (dev branch)

    @property
    def label(self) -> str:
        if self.tag:
            label = self.tag + (f"+{self.ahead}" if self.ahead else "")
            if self.dev:
                label += " (dev)"
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
    dev = _is_dev_clone(repo)
    tag = _newest_release_reachable(repo)
    ahead = 0
    if tag:
        count = _git(repo, "rev-list", "--count", f"{tag}..HEAD")
        if count and count.strip().isdigit():
            ahead = int(count.strip())
    dirty = bool((_git(repo, "status", "--porcelain") or "").strip())
    return ToolkitVersion(tag=tag, ahead=ahead, dirty=dirty, commit=commit, dev=dev)


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
    """Newest stable release tag on ``origin``, or None (no remote, no git, no network)."""
    return _latest_remote(repo, RELEASE_TAG_RE, timeout)


def latest_remote_dev_commit(repo: Path, timeout: float = 3.0) -> str | None:
    """Full sha of ``origin/dev`` when HEAD does not contain it yet, else None.

    None also covers no remote, no git and no network. A clone with local
    commits on top of ``origin/dev`` is not behind, so it gets None too.
    """
    output = _git(repo, "ls-remote", "origin", f"refs/heads/{DEV_BRANCH}", timeout=timeout)
    parts = (output or "").split()
    if not parts:
        return None
    if _git(repo, "merge-base", "--is-ancestor", parts[0], "HEAD") is not None:
        return None
    return parts[0]


def channel_notice(version: ToolkitVersion, stable: str | None, dev_commit: str | None = None) -> list[str]:
    """Lines telling the user how their clone relates to what ``origin`` offers.

    A stable clone only hears about newer stable releases. A dev clone is
    always told it is a development build, which stable release to prefer, and
    whether ``origin/dev`` has commits it does not have.
    """
    base = release_key(version.tag) if version.tag else None
    newer_stable = bool(stable and (base is None or release_key(stable) > base))
    if not version.dev:
        if newer_stable:
            return [f"A newer release is available: {stable} (this clone has {version.tag or 'no release'})."]
        return []
    lines = ["This clone is a development build; releases from main are the stable ones."]
    if newer_stable:
        lines.append(f"A newer stable release exists: {stable}. Go back to it with: git switch main && git pull")
    elif stable:
        lines.append(f"The latest stable release is {stable}.")
    if dev_commit and version.commit and not dev_commit.startswith(version.commit):
        lines.append(
            f"origin/dev has newer commits ({dev_commit[:7]}); "
            "update with: python3 scripts/install.py --update --pull"
        )
    return lines


def pull_status(repo: Path) -> tuple[bool, str]:
    """Whether ``git pull --ff-only`` is safe, and why it is not.

    True only on a branch with an upstream, with a clean working tree whose
    upstream is ahead and contains HEAD, or when HEAD already contains the
    commit of a newer release on ``origin`` but not its tag.
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
            # CI tags a commit after pushing it, so the clone may already have
            # the tagged code while lacking the tag. `pull` fetches tags, so a
            # newer remote release still makes pulling the useful thing to do,
            # but only when HEAD contains the tagged commit: on dev the release
            # tag sits on main's merge commit, which pulling dev never brings.
            release = _newest_release_reachable(repo)
            remote_release = latest_remote_release(repo)
            if remote_release and (release is None or release_key(remote_release) > release_key(release)):
                tagged = _remote_tag_commit(repo, remote_release)
                if tagged and _git(repo, "merge-base", "--is-ancestor", tagged, "HEAD") is not None:
                    return True, f"origin has a newer release ({remote_release}); pulling fetches its tag."
        return False, f"Already up to date with {upstream}."
    if _git(repo, "merge-base", "--is-ancestor", "HEAD", upstream) is None:
        return False, f"Your branch and {upstream} have diverged; pull yourself."
    return True, f"{upstream} has new commits; updating is safe."


def pull(repo: Path) -> tuple[bool, str]:
    """Run ``git pull --ff-only --tags``; returns (ok, output shown to the user).

    ``--tags`` so a release tag created after the last fetch arrives even when
    the branch itself is already up to date (the update notice compares tags).
    """
    output = _git(repo, "pull", "--ff-only", "--tags", timeout=60)
    if output is None:
        return False, "git pull --ff-only failed; pull in a terminal to see why."
    return True, output.strip() or "Already up to date."


def _short_sha(repo: Path) -> str | None:
    output = _git(repo, "rev-parse", "--short", "HEAD")
    if output is None:
        return None
    return output.strip() or None


def _latest_remote(repo: Path, pattern: re.Pattern, timeout: float) -> str | None:
    output = _git(repo, "ls-remote", "--tags", "--refs", "origin", timeout=timeout)
    tags = []
    for line in (output or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        tag = parts[1][len("refs/tags/"):]
        if pattern.match(tag):
            tags.append(tag)
    return max(tags, key=release_key) if tags else None


def _remote_tag_commit(repo: Path, tag: str) -> str | None:
    """Commit a tag on ``origin`` points to (peeled when annotated), or None."""
    ref = f"refs/tags/{tag}"
    output = _git(repo, "ls-remote", "origin", ref, ref + "^{}")
    shas = {}
    for line in (output or "").splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            shas[parts[1]] = parts[0]
    return shas.get(ref + "^{}") or shas.get(ref)


def _is_dev_clone(repo: Path) -> bool:
    """On the dev branch."""
    branch = (_git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    return branch == DEV_BRANCH


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
