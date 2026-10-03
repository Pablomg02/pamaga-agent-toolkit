"""Plan installation actions from a selection, and apply them safely.

``plan_actions`` is pure: it compares a :class:`Selection` with the
``Installed`` records that ``state.scan`` produced and returns one
:class:`Action` per item (install, update, switch mode, remove, skip or
keep). ``apply_actions`` executes them: symlinks with ``os.symlink``,
copies built in a hidden sibling ``.<name>.pamaga-tmp`` and moved into
place with ``os.replace``, anything replaced moved to
``<base>/.pamaga-backups/<YYYYmmdd-HHMMSS>/<kind>s/`` when a backup is
wanted, and the per-harness manifest updated after each successful action.

Nothing here raises for a single failed action: it becomes a
``Result(ok=False, ...)`` and the remaining actions still run. Items the
toolkit did not install (an UNMANAGED entry, a FOREIGN_LINK, a MODIFIED
copy) are only touched when the selection forces them.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping

from installer.catalog import Catalog, Item, content_hash, list_files
from installer.harnesses import Harness
from installer.state import BACKUP_DIR, Installed, Manifest, Status, item_target
from installer.versions import ItemVersion

MODES = ("link", "copy")
_TMP_SUFFIX = ".pamaga-tmp"
_OLD_SUFFIX = ".pamaga-old"


@dataclass(frozen=True)
class Selection:
    """What the user wants installed, before the dependency closure."""

    harness_ids: frozenset[str]
    skills: frozenset[str]        # before dependency closure
    agents: frozenset[str]
    commands: bool                # install wrappers where supported
    mode: str                     # "link" | "copy"
    prune: bool = False           # remove managed items not selected (TUI: True)
    force: frozenset[str] = frozenset()  # f"{harness_id}:{kind}/{name}" allowed to overwrite
    keep_modes: bool = False      # installed items keep their mode; ``mode`` is for new ones


@dataclass(frozen=True)
class Action:
    """One change (or deliberate no-op) for one item in one harness."""

    op: str            # "install" | "update" | "switch" | "remove" | "skip" | "keep"
    harness_id: str
    kind: str
    name: str
    target: Path
    mode: str | None   # mode after the action
    backup: bool       # real files moved to the backup dir first
    from_version: str | None
    to_version: str | None
    reason: str        # one short human sentence
    commit: str | None = None  # source commit recorded in the manifest


@dataclass(frozen=True)
class Result:
    """What happened when one action was applied."""

    action: Action
    ok: bool
    message: str


def plan_actions(
    catalog: Catalog,
    harnesses: Iterable[Harness],
    scans: Mapping[str, Mapping[str, Installed]],
    selection: Selection,
    versions: Callable[[Item], ItemVersion],
) -> list[Action]:
    """Actions that make the harnesses match ``selection``.

    ``harnesses`` are the candidates (only ids in ``selection.harness_ids``
    are planned); ``scans`` maps a harness id to the ``state.scan`` result
    for it, and a missing entry means "nothing installed". ``versions``
    returns the version of an item and is injected so tests need no git.

    Wanted items are the skills in ``catalog.required_closure(selection.skills)``,
    the selected agents, and the command wrappers of wanted user-invocable
    skills in harnesses that support commands. Wanted items are installed,
    updated or switched to the chosen mode (with ``keep_modes``, items
    already installed keep theirs and only new ones use ``mode``); not-wanted items are removed
    only with ``prune``. MODIFIED, UNMANAGED and FOREIGN_LINK entries are
    skipped until their ``force`` key (``f"{harness_id}:{kind}/{name}"``)
    is in the selection; then they are replaced, with a backup.
    """
    if selection.mode not in MODES:
        raise ValueError(f"unknown mode: {selection.mode!r} (expected 'link' or 'copy')")
    wanted_skills = catalog.required_closure(set(selection.skills))
    actions: list[Action] = []
    for harness in harnesses:
        if harness.id not in selection.harness_ids:
            continue
        scanned = scans.get(harness.id, {})
        actions.extend(
            _plan_harness(catalog, harness, scanned, selection, wanted_skills, versions)
        )
    return actions


def apply_actions(
    actions: Iterable[Action],
    catalog: Catalog,
    harnesses: Iterable[Harness],
    *,
    now: datetime,
    on_progress: Callable[[int, int, Result], None] | None = None,
) -> list[Result]:
    """Apply ``actions`` in order and return one :class:`Result` for each.

    Symlinks are removed with ``unlink``, never ``rmtree``. Copies are built
    in a hidden sibling ``.<name>.pamaga-tmp`` and swapped into place, so a
    failure leaves the previous install intact. Real entries that are
    overwritten with ``backup`` go to
    ``<base>/.pamaga-backups/<YYYYmmdd-HHMMSS>/<kind>s/`` first.

    A single failed action never raises and never stops the run: it becomes
    ``Result(ok=False, ...)``. Manifests touched by successful actions are
    saved once at the end, also when some action failed; ``on_progress``
    (when given) is called after every action with ``(done, total, result)``.
    """
    action_list = list(actions)
    by_id = {harness.id: harness for harness in harnesses}
    manifests: dict[str, Manifest] = {}
    dirty: set[str] = set()
    results: list[Result] = []
    total = len(action_list)
    for index, action in enumerate(action_list):
        try:
            message = _apply_one(action, catalog, by_id, manifests, dirty, now)
            result = Result(action=action, ok=True, message=message)
        except Exception as exc:  # one failed action never stops the rest
            result = Result(action=action, ok=False, message=_error_text(exc))
        results.append(result)
        if on_progress is not None:
            on_progress(index + 1, total, result)
    for harness_id in sorted(dirty):
        try:
            manifests[harness_id].save()
        except OSError:
            # The manifest is a record, not the install itself: a failed
            # write does not undo the actions and must not raise here.
            pass
    return results


def _plan_harness(
    catalog: Catalog,
    harness: Harness,
    scanned: Mapping[str, Installed],
    selection: Selection,
    wanted_skills: set[str],
    versions: Callable[[Item], ItemVersion],
) -> list[Action]:
    actions: list[Action] = []
    for kind, items in (
        ("skill", catalog.skills),
        ("agent", catalog.agents),
        ("command", catalog.commands),
    ):
        for item in items:
            installed = scanned.get(item.key)
            if installed is None:
                installed = _not_installed(harness, kind, item.name)
            wanted = _is_wanted(catalog, harness, item, selection, wanted_skills)
            action = _plan_item(harness, item, installed, wanted, selection, versions)
            if action is not None:
                actions.append(action)
    known = {
        item.key
        for items in (catalog.skills, catalog.agents, catalog.commands)
        for item in items
    }
    for key, installed in scanned.items():
        if key in known or installed.status != Status.ORPHANED:
            continue
        if selection.prune:
            actions.append(
                _remove_action(
                    harness,
                    installed,
                    backup=installed.mode == "copy",
                    reason="no longer in the toolkit",
                )
            )
    return actions


def _plan_item(
    harness: Harness,
    item: Item,
    installed: Installed,
    wanted: bool,
    selection: Selection,
    versions: Callable[[Item], ItemVersion],
) -> Action | None:
    if not wanted:
        return _plan_unwanted(harness, item, installed, selection)
    status = installed.status
    if status == Status.ORPHANED:
        # Ours, but the source it pointed at is gone: prune cleans it up.
        if selection.prune:
            return _remove_action(
                harness,
                installed,
                backup=installed.mode == "copy",
                reason="no longer in the toolkit",
            )
        return None
    version = versions(item)
    to_version = version.label
    commit = version.commit
    if status == Status.NOT_INSTALLED:
        return _make(
            "install", harness, item, installed, selection.mode, False, to_version, "not installed",
            commit,
        )
    if status in (Status.LINKED, Status.UP_TO_DATE):
        if selection.keep_modes or installed.mode == selection.mode:
            reason = "up to date" if status == Status.UP_TO_DATE else "linked"
            return _keep(harness, item, installed, reason)
        return _make(
            "switch",
            harness,
            item,
            installed,
            selection.mode,
            False,
            to_version,
            f"switching to {selection.mode}",
            commit,
        )
    if status == Status.OUTDATED:
        if selection.keep_modes or selection.mode == "copy":
            return _make(
                "update",
                harness,
                item,
                installed,
                "copy",
                False,
                to_version,
                "newer version available",
                commit,
            )
        return _make(
            "switch", harness, item, installed, "link", False, to_version, "switching to link",
            commit,
        )
    if status == Status.FOREIGN_LINK and not os.path.exists(installed.target):
        # A broken symlink (for example into a clone that was moved): nothing
        # can be lost by replacing it, and the old link is still backed up.
        return _make(
            "install", harness, item, installed, selection.mode, True, to_version,
            "broken symlink; replacing it", commit,
        )
    # MODIFIED, UNMANAGED or FOREIGN_LINK: not ours to replace without force.
    if _force_key(harness.id, item.key) not in selection.force:
        return _skip(harness, item, installed, _skip_reason(status))
    if status == Status.MODIFIED and selection.mode == "copy":
        return _make(
            "update",
            harness,
            item,
            installed,
            "copy",
            True,
            to_version,
            _replace_reason(status),
            commit,
        )
    return _make(
        "install", harness, item, installed, selection.mode, True, to_version,
        _replace_reason(status), commit,
    )


def _plan_unwanted(
    harness: Harness,
    item: Item,
    installed: Installed,
    selection: Selection,
) -> Action | None:
    status = installed.status
    if item.kind == "command" and not harness.supports_commands:
        reason = "commands are not supported by this harness"
    elif item.kind == "agent" and not harness.supports_agents:
        reason = "agents use another layout in this harness"
    elif item.kind == "skill" and _reads_shared_skills(harness, selection):
        providers = [p for p in harness.skills_from if p in selection.harness_ids]
        reason = f"already read from the {', '.join(providers)} skills"
    else:
        reason = "no longer selected"
    if status == Status.UP_TO_DATE and not installed.managed:
        # An identical copy the user made by hand: not ours to delete.
        return _keep(harness, item, installed, reason)
    if status in (Status.LINKED, Status.UP_TO_DATE, Status.OUTDATED):
        if selection.prune:
            return _remove_action(harness, installed, backup=False, reason=reason)
        return _keep(harness, item, installed, reason)
    if status == Status.MODIFIED:
        if selection.prune and _force_key(harness.id, item.key) in selection.force:
            return _remove_action(
                harness, installed, backup=True, reason="modified locally; removed with a backup"
            )
        return _keep(harness, item, installed, reason)
    if status == Status.ORPHANED:
        if selection.prune:
            return _remove_action(
                harness,
                installed,
                backup=installed.mode == "copy",
                reason="no longer in the toolkit",
            )
        return None
    # NOT_INSTALLED, UNMANAGED and FOREIGN_LINK are left alone.
    return None


def _reads_shared_skills(harness: Harness, selection: Selection) -> bool:
    """True when this harness already sees the skills installed for another selected one."""
    return any(provider in selection.harness_ids for provider in harness.skills_from)


def _is_wanted(
    catalog: Catalog,
    harness: Harness,
    item: Item,
    selection: Selection,
    wanted_skills: set[str],
) -> bool:
    if item.kind == "skill":
        # opencode also reads the Claude Code dirs and, in project scope, the
        # Antigravity .agents dir: installing here as well would list every
        # skill twice. See skills_from in harnesses.py.
        return item.name in wanted_skills and not _reads_shared_skills(harness, selection)
    if item.kind == "agent":
        return item.name in selection.agents and harness.supports_agents
    skill = catalog.get("skill", item.name)
    return bool(
        selection.commands
        and harness.supports_commands
        and skill is not None
        and skill.user_invocable
        and skill.name in wanted_skills
    )


def _not_installed(harness: Harness, kind: str, name: str) -> Installed:
    return Installed(
        harness_id=harness.id,
        kind=kind,
        name=name,
        target=item_target(harness, kind, name),
        status=Status.NOT_INSTALLED,
        mode=None,
        installed_version=None,
        link_target=None,
        changed_files=(),
    )


def _make(
    op: str,
    harness: Harness,
    item: Item,
    installed: Installed,
    mode: str | None,
    backup: bool,
    to_version: str | None,
    reason: str,
    commit: str | None = None,
) -> Action:
    return Action(
        op=op,
        harness_id=harness.id,
        kind=item.kind,
        name=item.name,
        target=installed.target,
        mode=mode,
        backup=backup,
        from_version=installed.installed_version,
        to_version=to_version,
        reason=reason,
        commit=commit,
    )


def _keep(harness: Harness, item: Item, installed: Installed, reason: str) -> Action:
    return _make(
        "keep", harness, item, installed, installed.mode, False, installed.installed_version, reason
    )


def _skip(harness: Harness, item: Item, installed: Installed, reason: str) -> Action:
    return _make(
        "skip", harness, item, installed, installed.mode, False, installed.installed_version, reason
    )


def _remove_action(harness: Harness, installed: Installed, backup: bool, reason: str) -> Action:
    return Action(
        op="remove",
        harness_id=harness.id,
        kind=installed.kind,
        name=installed.name,
        target=installed.target,
        mode=None,
        backup=backup,
        from_version=installed.installed_version,
        to_version=None,
        reason=reason,
    )


def _skip_reason(status: Status) -> str:
    if status == Status.MODIFIED:
        return "modified locally; select to overwrite"
    if status == Status.UNMANAGED:
        return "not installed by the toolkit; select to overwrite"
    return "symlink points elsewhere; select to overwrite"


def _replace_reason(status: Status) -> str:
    if status == Status.MODIFIED:
        return "modified locally; overwriting with a backup"
    if status == Status.UNMANAGED:
        return "not installed by the toolkit; overwriting with a backup"
    return "symlink points elsewhere; overwriting with a backup"


def _force_key(harness_id: str, key: str) -> str:
    return f"{harness_id}:{key}"


def _apply_one(
    action: Action,
    catalog: Catalog,
    by_id: Mapping[str, Harness],
    manifests: dict[str, Manifest],
    dirty: set[str],
    now: datetime,
) -> str:
    if action.op == "keep":
        _adopt(action, catalog, by_id, manifests, dirty, now)
        return action.reason or "unchanged"
    if action.op == "skip":
        return action.reason or "skipped"
    harness = by_id.get(action.harness_id)
    if harness is None:
        raise ValueError(f"no harness named {action.harness_id!r}")
    if action.op == "remove":
        manifest = _manifest_for(harness, catalog, manifests)
        _remove(action, harness, manifest, now)
        dirty.add(harness.id)
        return "removed" + (" (backup kept)" if action.backup else "")
    if action.op in ("install", "update", "switch"):
        item = catalog.get(action.kind, action.name)
        if item is None:
            raise ValueError(f"{action.kind}/{action.name} is not in the catalog any more")
        if action.mode == "link":
            _link(item, action, harness, now)
        elif action.mode == "copy":
            _copy(item, action, harness, now)
        else:
            raise ValueError(f"unknown mode: {action.mode!r}")
        manifest = _manifest_for(harness, catalog, manifests)
        manifest.record(
            item.key,
            mode=action.mode,
            hash=item.content_hash,
            version=action.to_version,
            commit=action.commit,
            installed_at=now.isoformat(),
        )
        dirty.add(harness.id)
        messages = {"install": "installed", "update": "updated", "switch": f"switched to {action.mode}"}
        return messages[action.op]
    raise ValueError(f"unknown action: {action.op!r}")


def _adopt(
    action: Action,
    catalog: Catalog,
    by_id: Mapping[str, Harness],
    manifests: dict[str, Manifest],
    dirty: set[str],
    now: datetime,
) -> None:
    """Record a kept copy that is identical to the source but has no record.

    Copies made by hand (docs/INSTALL.md, option 2) or by an older script
    are then tracked, so the next change upstream shows up as an update
    instead of as a copy "not installed by the toolkit".
    """
    harness = by_id.get(action.harness_id)
    item = catalog.get(action.kind, action.name)
    if harness is None or item is None or action.mode != "copy":
        return
    manifest = _manifest_for(harness, catalog, manifests)
    key = f"{action.kind}/{action.name}"
    if manifest.get(key) is not None or os.path.islink(action.target):
        return
    if not os.path.exists(action.target) or content_hash(action.target) != item.content_hash:
        return
    manifest.record(
        key, mode="copy", hash=item.content_hash, version=action.to_version,
        commit=action.commit, installed_at=now.isoformat(),
    )
    dirty.add(harness.id)


def _manifest_for(
    harness: Harness, catalog: Catalog, manifests: dict[str, Manifest]
) -> Manifest:
    manifest = manifests.get(harness.id)
    if manifest is None:
        manifest = Manifest.load(harness.base)
        manifest.repo = catalog.repo  # so the JSON knows which clone this is
        manifests[harness.id] = manifest
    return manifest


def _link(item: Item, action: Action, harness: Harness, now: datetime) -> None:
    target = action.target
    target.parent.mkdir(parents=True, exist_ok=True)
    moved = _move_aside(target, action, harness, now)
    try:
        os.symlink(item.source, target, target_is_directory=item.is_dir)
    except OSError as exc:
        _restore(moved, target)
        raise OSError(f"{exc}; use copy mode or enable Developer Mode (Windows)") from exc
    _finish_move(moved, action)


def _copy(item: Item, action: Action, harness: Harness, now: datetime) -> None:
    target = action.target
    tmp = _tmp_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _remove_path(tmp)  # a temp left behind by an interrupted run
    try:
        _write_copy(item, tmp)
    except Exception:
        _remove_path(tmp)
        raise
    moved = _move_aside(target, action, harness, now)
    try:
        os.replace(tmp, target)
    except OSError:
        _remove_path(tmp)
        _restore(moved, target)
        raise
    _finish_move(moved, action)


def _write_copy(item: Item, destination: Path) -> None:
    """Copy ``item`` to ``destination``; only ``list_files`` entries."""
    if item.source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for relative in list_files(item.source):
            copied = destination / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source / relative, copied)
    else:
        shutil.copy2(item.source, destination)


def _move_aside(
    target: Path, action: Action, harness: Harness, now: datetime
) -> Path | None:
    """Move an existing target out of the way; its new path, or None.

    With ``action.backup`` the entry goes to the backup directory and
    stays there; otherwise it goes to the hidden ``.pamaga-old`` sibling
    that the caller deletes after the swap.
    """
    if not os.path.lexists(target):
        return None
    if action.backup:
        destination = _unique(_backup_dir(harness, action, now) / action.target.name)
    else:
        destination = _old_path(target)
        _remove_path(destination)
    _move(target, destination)
    return destination


def _finish_move(moved: Path | None, action: Action) -> None:
    if moved is not None and not action.backup:
        _remove_path(moved)


def _restore(moved: Path | None, target: Path) -> None:
    if moved is not None:
        _move(moved, target)


def _remove(action: Action, harness: Harness, manifest: Manifest, now: datetime) -> None:
    target = action.target
    if os.path.islink(target):
        target.unlink()  # never rmtree a symlink: that would delete its target
    elif not os.path.lexists(target):
        pass  # a stale manifest entry; nothing on disk any more
    elif action.backup:
        _move(target, _unique(_backup_dir(harness, action, now) / action.target.name))
    elif target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    manifest.forget(f"{action.kind}/{action.name}")


def _backup_dir(harness: Harness, action: Action, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return harness.base / BACKUP_DIR / stamp / harness.dir_for(action.kind).name


def _tmp_path(target: Path) -> Path:
    return target.with_name("." + target.name + _TMP_SUFFIX)


def _old_path(target: Path) -> Path:
    return target.with_name("." + target.name + _OLD_SUFFIX)


def _move(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _remove_path(path: Path) -> None:
    """Delete a file, a symlink or a real directory (never through a link)."""
    if os.path.islink(path):
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif os.path.lexists(path):
        path.unlink()


def _unique(path: Path) -> Path:
    """``path`` or the first free ``path-2``, ``path-3``... (same second)."""
    candidate = path
    counter = 1
    while os.path.lexists(candidate):
        counter += 1
        candidate = path.with_name(f"{path.name}-{counter}")
    return candidate


def _error_text(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__
