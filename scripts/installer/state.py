"""What the toolkit installed in each harness, and how it changed since.

The manifest (`<base>/.pamaga-toolkit.json`) records what the installer
created in one harness base, with the content hash and version it had at
install time. Comparing that record with the current sources and with the
files on disk tells *up to date*, *outdated*, *modified locally* and
*leftover* apart without guessing.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from installer.catalog import Catalog, content_hash, list_files
from installer.harnesses import Harness

MANIFEST_NAME = ".pamaga-toolkit.json"
BACKUP_DIR = ".pamaga-backups"
SCHEMA = 1

KIND_DIRS = ("skill", "agent", "command")
FILE_KINDS = ("agent", "command")


class Status(str, Enum):
    """What lives at the target path of one catalog item in one harness."""

    NOT_INSTALLED = "not-installed"
    LINKED = "linked"
    UP_TO_DATE = "up-to-date"
    OUTDATED = "outdated"
    MODIFIED = "modified"
    UNMANAGED = "unmanaged"
    FOREIGN_LINK = "foreign-link"
    ORPHANED = "orphaned"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Installed:
    """One catalog item as found in one harness base."""

    harness_id: str
    kind: str
    name: str
    target: Path
    status: Status
    mode: str | None
    installed_version: str | None
    link_target: str | None
    changed_files: tuple[str, ...]
    # True when the manifest has a record for it: the toolkit put it there.
    managed: bool = False

    @property
    def key(self) -> str:
        return f"{self.kind}/{self.name}"


class Manifest:
    """Install record of one harness base, stored next to the items."""

    def __init__(self, base: Path, repo: Path | None = None) -> None:
        self.base = Path(base)
        self.repo = repo
        self.items: dict[str, dict] = {}

    @property
    def path(self) -> Path:
        return self.base / MANIFEST_NAME

    @classmethod
    def load(cls, base: Path) -> "Manifest":
        """Read `<base>/.pamaga-toolkit.json`.

        A missing file yields an empty manifest. A file we cannot read as
        a manifest is moved to `<name>.bak` and treated as empty, so the
        user keeps whatever it was and the installer can start over.
        """
        manifest = cls(base)
        path = manifest.path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return manifest
        except ValueError:  # not UTF-8: corrupt, keep it as a backup
            _set_aside(path)
            return manifest
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
            _set_aside(path)
            return manifest
        repo = data.get("repo")
        if isinstance(repo, str) and repo:
            manifest.repo = Path(repo)
        manifest.items = {
            key: value
            for key, value in data["items"].items()
            if isinstance(key, str) and isinstance(value, dict)
        }
        return manifest

    def get(self, key: str) -> dict | None:
        """The recorded entry for "kind/name", or None."""
        return self.items.get(key)

    def record(
        self,
        key: str,
        *,
        mode: str,
        hash: str,
        version: str | None,
        commit: str | None,
        installed_at: str,
    ) -> None:
        """Remember an item installed just now (upsert)."""
        self.items[key] = {
            "mode": mode,
            "hash": hash,
            "version": version,
            "commit": commit,
            "installed_at": installed_at,
        }

    def forget(self, key: str) -> None:
        """Drop an item from the record (no error when it is not there)."""
        self.items.pop(key, None)

    def save(self) -> None:
        """Write the manifest atomically, creating the base directory.

        The JSON goes to a temporary file next to the manifest and is
        moved into place with `os.replace`, so a crash never leaves a
        half-written manifest behind.
        """
        self.base.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": SCHEMA,
            "repo": str(self.repo) if self.repo is not None else None,
            "items": self.items,
        }
        tmp = self.path.with_name(MANIFEST_NAME + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass


def item_target(harness: Harness, kind: str, name: str) -> Path:
    """Path an item gets in a harness: `<dir>/<name>` or `<dir>/<name>.md`."""
    filename = name + ".md" if kind in FILE_KINDS else name
    return harness.dir_for(kind) / filename


def scan(catalog: Catalog, harness: Harness, manifest: Manifest) -> dict[str, Installed]:
    """Report every catalog item in `harness`, plus its leftovers.

    The result has one `Installed` per catalog item (key "kind/name") and
    `ORPHANED` entries for manifest keys whose source is gone and for
    dangling symlinks that point into the repository. Commands are scanned
    even for harnesses that do not support them, because older installer
    versions linked them there and they must be found to be cleaned up.
    """
    repo = os.path.realpath(str(catalog.repo))
    result: dict[str, Installed] = {}
    groups = (
        ("skill", catalog.skills),
        ("agent", catalog.agents),
        ("command", catalog.commands),
    )
    for kind, items in groups:
        for item in items:
            result[item.key] = _inspect(
                repo, harness, manifest, kind, item.name, item.source, item.content_hash
            )
    for key in sorted(manifest.items):
        if key in result:
            continue
        parsed = _split_key(key)
        if parsed is not None:
            result[key] = _orphan_from_manifest(harness, manifest, parsed[0], parsed[1])
    for kind, _ in groups:
        directory = harness.dir_for(kind)
        if not directory.is_dir():
            continue
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_symlink():
                continue
            resolved = os.path.realpath(str(entry))
            if os.path.exists(resolved) or not _is_under(resolved, repo):
                continue
            name = _item_name(kind, entry.name)
            key = f"{kind}/{name}"
            if key in result:
                continue
            result[key] = Installed(
                harness_id=harness.id,
                kind=kind,
                name=name,
                target=entry,
                status=Status.ORPHANED,
                mode="link",
                installed_version=(manifest.get(key) or {}).get("version"),
                link_target=os.readlink(str(entry)),
                changed_files=(),
                managed=True,
            )
    return result


def _inspect(
    repo: str,
    harness: Harness,
    manifest: Manifest,
    kind: str,
    name: str,
    source: Path,
    source_hash: str,
) -> Installed:
    """Classify one catalog item against what is on disk."""
    target = item_target(harness, kind, name)
    record = manifest.get(f"{kind}/{name}")
    if os.path.islink(target):
        link = os.readlink(str(target))
        resolved = os.path.realpath(str(target))
        if resolved == os.path.realpath(str(source)):
            status = Status.LINKED
        elif not os.path.exists(resolved) and _is_under(resolved, repo):
            status = Status.ORPHANED
        else:
            status = Status.FOREIGN_LINK
        return _installed(harness, kind, name, target, status, "link", record, link, ())
    if target.exists():
        current = content_hash(target)
        if current == source_hash:
            return _installed(
                harness, kind, name, target, Status.UP_TO_DATE, "copy", record, None, ()
            )
        changed = _changed_files(target, source)
        if record is not None and record.get("hash") == current:
            status = Status.OUTDATED
        elif record is not None:
            status = Status.MODIFIED
        else:
            status = Status.UNMANAGED
        return _installed(harness, kind, name, target, status, "copy", record, None, changed)
    mode = record.get("mode") if record is not None else None
    return _installed(harness, kind, name, target, Status.NOT_INSTALLED, mode, record, None, ())


def _installed(
    harness: Harness,
    kind: str,
    name: str,
    target: Path,
    status: Status,
    mode: str | None,
    record: dict | None,
    link_target: str | None,
    changed_files: tuple[str, ...],
) -> Installed:
    return Installed(
        harness_id=harness.id,
        kind=kind,
        name=name,
        target=target,
        status=status,
        mode=mode,
        installed_version=record.get("version") if record is not None else None,
        link_target=link_target,
        changed_files=changed_files,
        managed=record is not None,
    )


def _orphan_from_manifest(harness: Harness, manifest: Manifest, kind: str, name: str) -> Installed:
    """An item we recorded whose source no longer exists in the repository."""
    target = item_target(harness, kind, name)
    record = manifest.get(f"{kind}/{name}") or {}
    link_target = None
    mode = record.get("mode")
    if os.path.islink(target):
        mode = "link"
        link_target = os.readlink(str(target))
    elif os.path.lexists(target):
        # Real files where we recorded a link: someone replaced it by hand,
        # so removing it must keep a backup.
        mode = "copy"
    return Installed(
        harness_id=harness.id,
        kind=kind,
        name=name,
        target=target,
        status=Status.ORPHANED,
        mode=mode,
        installed_version=record.get("version"),
        link_target=link_target,
        changed_files=(),
        managed=True,
    )


def _changed_files(target: Path, source: Path) -> tuple[str, ...]:
    """Differences between an installed item and its source, per file.

    "+ x" is only in the installed copy (added by hand, or no longer part
    of the toolkit), "- x" is in the source but missing from the copy and
    "~ x" has different content. Additions come first, then removals, then
    modifications, each group sorted by path.
    """
    target_hashes = _rel_hashes(target)
    source_hashes = _rel_hashes(source)
    changes = []
    for rel in sorted(set(target_hashes) - set(source_hashes)):
        changes.append("+ " + rel)
    for rel in sorted(set(source_hashes) - set(target_hashes)):
        changes.append("- " + rel)
    for rel in sorted(set(source_hashes) & set(target_hashes)):
        if target_hashes[rel] != source_hashes[rel]:
            changes.append("~ " + rel)
    return tuple(changes)


def _rel_hashes(path: Path) -> dict[str, str]:
    """sha256 of each file of `path`, keyed by its relative posix path."""
    is_dir = path.is_dir()
    hashes: dict[str, str] = {}
    for rel in list_files(path):
        file_path = path / rel if is_dir else path
        try:
            hashes[rel] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError:
            continue
    return hashes


def _split_key(key: str) -> tuple[str, str] | None:
    """Split a manifest key, or None when it cannot name an item."""
    kind, _, name = key.partition("/")
    if kind not in KIND_DIRS or not name or "/" in name:
        return None
    return kind, name


def _item_name(kind: str, entry_name: str) -> str:
    """Item name of an entry in a harness directory (drops the .md)."""
    if kind in FILE_KINDS and entry_name.endswith(".md"):
        return entry_name[:-3]
    return entry_name


def _is_under(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent.rstrip(os.sep) + os.sep)


def _set_aside(path: Path) -> None:
    """Keep an unreadable manifest as `<name>.bak` instead of deleting it."""
    backup = path.with_name(path.name + ".bak")
    try:
        os.replace(path, backup)
    except OSError:
        pass
