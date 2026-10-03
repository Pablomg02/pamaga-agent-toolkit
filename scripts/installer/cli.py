"""Non-interactive interface of the installer, and the TUI's entry point.

``main`` implements the CLI: ``--yes`` installs a selection, ``--update``
updates what is already installed (optionally pulling the clone first with
``--pull``), ``--status`` prints what is installed, ``--uninstall`` removes
everything the toolkit installed, ``--version`` prints the toolkit label. With no action flags it
runs the TUI when stdin and stdout are terminals, and prints the usage to
stderr with exit code 2 otherwise.

The CLI never removes items the user did not select unless ``--prune`` or
``--uninstall`` is given, and never touches UNMANAGED or FOREIGN items
without ``--force`` (which always keeps a backup).

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from installer import versions
from installer.actions import (
    Action,
    Selection,
    apply_actions,
    plan_actions,
    shared_skill_losses,
    shared_source,
)
from installer.catalog import Catalog, Item, load_catalog
from installer.harnesses import Harness, all_harnesses
from installer.state import BACKUP_DIR, Installed, Manifest, Status, scan
from installer.versions import ItemVersion, latest_remote_dev_commit, latest_remote_release, pull, pull_status, toolkit_version

REPO = Path(__file__).resolve().parents[2]

USAGE = """Usage:
  python3 scripts/install.py                 # TUI when stdin and stdout are TTYs; else help, exit 2
  python3 scripts/install.py --yes [--harness opencode,claude,antigravity|all] [--skills all|a,b]
                           [--agents all|a,b] [--mode link|copy] [--no-commands]
                           [--scope user|project] [--prune] [--force]
  python3 scripts/install.py --update [--pull] [--harness ...] [--mode link|copy] [--force]
  python3 scripts/install.py --status [--json] [--harness ...]
  python3 scripts/install.py --uninstall [--harness ...] [--force]
  python3 scripts/install.py --version
Common: --offline, --no-color, --ascii"""

STATUS_MARK = {
    Status.LINKED: "=",
    Status.UP_TO_DATE: "*",
    Status.OUTDATED: "^",
    Status.MODIFIED: "~",
    Status.UNMANAGED: "!",
    Status.FOREIGN_LINK: "!",
    Status.ORPHANED: "x",
    Status.NOT_INSTALLED: ".",
}
MANAGED = (Status.LINKED, Status.UP_TO_DATE, Status.OUTDATED, Status.MODIFIED)
STATUS_WORDS = {
    Status.LINKED: "linked",
    Status.UP_TO_DATE: "up to date",
    Status.OUTDATED: "outdated",
    Status.MODIFIED: "modified",
    Status.UNMANAGED: "not ours",
    Status.FOREIGN_LINK: "not ours",
    Status.ORPHANED: "orphaned",
    Status.NOT_INSTALLED: "-",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="install.py", add_help=True, description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true", help="install the selection without asking")
    parser.add_argument("--update", action="store_true",
                        help="update what is already installed, in each harness, and nothing else")
    parser.add_argument("--pull", action="store_true",
                        help="with --yes or --update: first update the clone (git pull --ff-only)")
    parser.add_argument("--status", action="store_true", help="show what is installed")
    parser.add_argument("--uninstall", action="store_true", help="remove everything the toolkit installed")
    parser.add_argument("--harness", metavar="IDS", help="comma-separated harness ids or 'all'")
    parser.add_argument("--skills", default="all", metavar="all|NAMES", help="skills to install")
    parser.add_argument("--agents", default="all", metavar="all|NAMES", help="agents to install")
    parser.add_argument(
        "--mode", choices=("link", "copy"),
        help="install mode (default: what is installed keeps its mode; new items are linked, "
             "or copied on Windows or when everything installed is a copy)",
    )
    parser.add_argument("--no-commands", action="store_true", help="skip the opencode command wrappers")
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--prune", action="store_true", help="remove managed items not selected")
    parser.add_argument("--force", action="store_true", help="also replace modified or unmanaged items, with a backup")
    parser.add_argument("--json", action="store_true", help="machine-readable --status")
    parser.add_argument("--version", action="store_true", help="print the toolkit version")
    parser.add_argument("--offline", action="store_true", help="never touch the network")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--ascii", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(toolkit_version(REPO).label)
        return 0

    if sum(bool(flag) for flag in (args.yes, args.update, args.status, args.uninstall)) > 1:
        parser.error("use only one of --yes, --update, --status and --uninstall")
    if not (args.yes or args.update or args.status or args.uninstall):
        if sys.stdin.isatty() and sys.stdout.isatty():
            return run_tui(args)
        print(USAGE, file=sys.stderr)
        return 2
    if args.pull:
        if not (args.yes or args.update):
            parser.error("--pull only works with --yes or --update")
        if not _pull_clone(args):
            return 1

    catalog = load_catalog(REPO)
    if args.status:
        return print_status(args, catalog)

    harnesses = resolve_harnesses(args)
    everyone, scans = scan_all(catalog, args)
    if args.uninstall:
        force = frozenset(
            f"{harness.id}:{key}"
            for harness in harnesses
            for key, record in scans[harness.id].items()
            if record.status == Status.MODIFIED and args.force
        )
        selection = Selection(
            harness_ids=frozenset(h.id for h in harnesses),
            skills=frozenset(),
            agents=frozenset(),
            commands=False,
            mode="link",
            prune=True,
            force=force,
        )
    elif args.update:
        selection = None
    else:
        selection = Selection(
            harness_ids=frozenset(h.id for h in harnesses),
            skills=frozenset(parse_names(args.skills, catalog.skills, parser, "skill")),
            agents=frozenset(parse_names(args.agents, catalog.agents, parser, "agent")),
            commands=not args.no_commands,
            mode=args.mode or default_mode(harnesses, scans),
            prune=args.prune,
            keep_modes=args.mode is None,
            force=frozenset(
                f"{harness.id}:{key}"
                for harness in harnesses
                for key, record in scans[harness.id].items()
                if args.force
                and record.status in (Status.MODIFIED, Status.UNMANAGED, Status.FOREIGN_LINK)
            ),
        )

    if selection is None:
        actions = _plan_update(args, catalog, harnesses, scans)
        if not any(a.op != "skip" for a in actions) and not any(
            record.status in MANAGED for harness in harnesses for record in scans[harness.id].values()
        ):
            print("Nothing from the toolkit is installed yet; use --yes to install it.")
            return 0
    else:
        actions = plan_actions(catalog, harnesses, scans, selection, item_version_for(catalog))
    _print_plan(actions, harnesses, scans, catalog, uninstall=args.uninstall)
    for harness_id, name, provider in shared_skill_losses(everyone, scans, actions):
        print(f"Warning: {_label(everyone, harness_id)} read skill {name} from "
              f"{_label(everyone, provider)} and will no longer see it.")
    sys.stdout.flush()
    results = apply_actions(actions, catalog, harnesses, now=datetime.now().astimezone())
    failed = [result for result in results if not result.ok]
    for result in failed:
        print(f"  FAIL     {result.action.target}: {result.message}", file=sys.stderr)
    backups = [
        harness.base / BACKUP_DIR
        for harness in harnesses
        if any(
            result.ok and result.action and result.action.backup and result.action.harness_id == harness.id
            for result in results
        )
    ]
    if backups:
        print("Backups kept in: " + ", ".join(str(path) for path in backups))

    if args.uninstall:
        return 1 if failed else 0

    if selection is not None:
        notes = shared_notes(catalog, everyone, harnesses, scans, selection)
        kept = [a for a in actions
                if a.kind == "skill" and a.op == "keep" and a.reason.startswith("already read from")]
        if notes:
            print()
            for line in notes:
                print(line)
            if kept:
                print("Older copies in its own skills dir are kept; run with --prune to remove them.")
    changed = [a for a in actions if a.op not in ("keep", "skip")]
    print()
    skipped = sum(1 for a in actions if a.op == "skip")
    if args.update and not changed:
        print(f"Nothing updated: {skipped} item(s) skipped (see above)." if skipped
              else "Everything is up to date.")
    else:
        print("Done. Restart your agent to pick up the changes.")
    if not args.offline and not os.environ.get("PAMAGA_OFFLINE"):
        _remote_hint()
    return 1 if failed else 0


def _plan_update(args, catalog: Catalog, harnesses: List[Harness], scans) -> List[Action]:
    """Plan --update per harness: what each one already has, in its own mode.

    A skill installed only in opencode must not be added to Claude Code, and
    wrappers are only refreshed where some are installed already. Items keep
    their mode unless --mode is given, and leftovers whose source is gone
    from the toolkit are removed (copies with a backup). Nothing else is
    added or removed: a copy in opencode that Claude Code also has is
    refreshed, and so are the wrappers of skills opencode reads from it.
    """
    actions: List[Action] = []
    for harness in harnesses:
        scanned = scans[harness.id]
        own = [record for record in scanned.values() if record.status in MANAGED]
        if not own:
            continue
        force = frozenset(
            f"{harness.id}:{key}" for key, record in scanned.items()
            if args.force and record.status in (Status.MODIFIED, Status.UNMANAGED, Status.FOREIGN_LINK)
        )
        selection = Selection(
            harness_ids=frozenset({harness.id}),
            skills=frozenset(r.name for r in own if r.kind == "skill"),
            agents=frozenset(r.name for r in own if r.kind == "agent"),
            commands=any(r.kind == "command" for r in own),
            mode=args.mode or default_mode([harness], scans),
            # The selection is exactly what is installed, so pruning only
            # drops leftovers of items removed from the toolkit.
            prune=True,
            force=force,
            keep_modes=args.mode is None,
            keep_installed=True,
        )
        actions.extend(plan_actions(catalog, [harness], scans, selection, item_version_for(catalog)))
    return actions


def _pull_clone(args) -> bool:
    """git pull --ff-only when it is safe; False only when the pull itself failed.

    When pulling is not safe (local changes, no upstream...) it says why and
    the run goes on with the clone as it is.
    """
    if args.offline or os.environ.get("PAMAGA_OFFLINE"):
        print("--pull ignored: offline.")
        return True
    can, reason = pull_status(REPO)
    if not can:
        print(f"Not pulling: {reason}")
        return True
    ok, output = pull(REPO)
    print(output)
    versions.clear_cache()
    return ok


def _remote_hint() -> None:
    """Tell how this clone compares with origin's releases (3 s max per query)."""
    current = toolkit_version(REPO)
    stable = latest_remote_release(REPO, timeout=3.0)
    dev = latest_remote_dev_commit(REPO, timeout=3.0) if current.dev else None
    lines = versions.channel_notice(current, stable, dev)
    if lines:
        print()
        for line in lines:
            print(line)
        if not current.dev:
            print("Update with: python3 scripts/install.py --update --pull")


# -- helpers ---------------------------------------------------------------


def scan_all(catalog: Catalog, args) -> Tuple[List[Harness], Dict[str, Mapping[str, Installed]]]:
    """Every harness of the scope and its scan, selected or not.

    Unselected ones matter too: opencode reads ~/.claude/skills even when
    only opencode is being installed.
    """
    everyone = all_harnesses(args.scope, project=Path.cwd())
    return everyone, {h.id: scan(catalog, h, Manifest.load(h.base)) for h in everyone}


def shared_notes(
    catalog: Catalog,
    everyone: List[Harness],
    harnesses: List[Harness],
    scans: Mapping[str, Mapping[str, Installed]],
    selection: Selection,
) -> List[str]:
    """One line per selected harness that gets its skills from another one's dir."""
    wanted = catalog.required_closure(set(selection.skills))
    lines = []
    for harness in harnesses:
        providers: Dict[str, int] = {}
        for name in sorted(wanted):
            provider = shared_source(harness, name, scans, selection.harness_ids)
            if provider is not None:
                providers[provider] = providers.get(provider, 0) + 1
        for provider, count in providers.items():
            source = next(h for h in everyone if h.id == provider)
            lines.append(f"Note: {harness.label} reads {count} skill(s) from {source.dir_for('skill')} "
                         f"({source.label}), so they are not copied to its own dir.")
    return lines


def _label(harnesses: Iterable[Harness], harness_id: str) -> str:
    return next((h.label for h in harnesses if h.id == harness_id), harness_id)


def resolve_harnesses(args) -> List[Harness]:
    """Harnesses named by --harness, or sensible defaults per action."""
    known = {harness.id: harness for harness in all_harnesses(args.scope, project=Path.cwd())}
    if args.harness:
        if args.harness.strip() == "all":
            return list(known.values())
        names = [name.strip() for name in args.harness.split(",") if name.strip()]
        return [_known_harness(known, name) for name in names]
    if args.yes:
        detected = [harness for harness in known.values() if harness.detected()]
        return detected or [known["opencode"]]
    return list(known.values())


def _known_harness(known: Mapping[str, Harness], name: str) -> Harness:
    if name not in known:
        raise SystemExit(f"Unknown harness: {name!r}; expected one of {', '.join(sorted(known))}")
    return known[name]


def parse_names(value: str, items: Iterable[Item], parser: argparse.ArgumentParser, kind: str) -> List[str]:
    names = {item.name for item in items}
    if value == "all":
        return sorted(names)
    selected = [name.strip() for name in value.split(",") if name.strip()]
    for name in selected:
        if name not in names:
            parser.error(f"unknown {kind}: {name!r}")
    return selected


def default_mode(harnesses: Iterable[Harness], scans: Mapping[str, Mapping[str, object]]) -> str:
    """Link, or copy on Windows; an all-copy install history preselects copy."""
    modes = set()
    for harness in harnesses:
        for record in scans.get(harness.id, {}).values():
            mode = getattr(record, "mode", None)
            if mode and getattr(record, "status", None) in MANAGED:
                modes.add(mode)
    if modes == {"copy"}:
        return "copy"
    if modes:
        return "link"
    return "copy" if os.name == "nt" else "link"


def item_version_for(catalog: Catalog) -> Callable[[Item], ItemVersion]:
    def version_of(item: Item) -> ItemVersion:
        relative = item.source.relative_to(catalog.repo).as_posix()
        return versions.item_version(catalog.repo, relative)

    return version_of


def _print_plan(
    actions: List[Action],
    harnesses: List[Harness],
    scans: Mapping[str, Mapping[str, object]],
    catalog: Catalog,
    uninstall: bool,
) -> None:
    shown: set = set()
    for action in actions:
        if action.harness_id not in shown:
            shown.add(action.harness_id)
            harness = next(h for h in harnesses if h.id == action.harness_id)
            print(f"{harness.label} -> {harness.base}")
        line = _action_line(action, scans.get(action.harness_id, {}), catalog)
        if line is not None:
            print("  " + line)


def _action_line(action: Action, scanned: Mapping[str, object], catalog: Catalog) -> Optional[str]:
    target = action.target
    if action.op == "skip":
        message = f"SKIP     {target}"
        if action.reason:
            message += " " + action.reason.replace("select to overwrite", "use --force to overwrite")
        sys.stdout.flush()
        print("  " + message, file=sys.stderr)
        return None
    if action.op == "keep":
        return f"ok       {target}"
    suffix = " (backup kept)" if action.backup else ""
    if action.op == "install":
        if action.mode == "link":
            item = catalog.get(action.kind, action.name)
            source = item.source if item is not None else ""
            return f"link     {target} -> {source}{suffix}"
        return f"copy     {target}{suffix}"
    if action.op == "update":
        return f"update   {target} ({action.from_version or '?'} -> {action.to_version}){suffix}"
    if action.op == "switch":
        return f"switch   {target} (to {action.mode})"
    record = scanned.get(f"{action.kind}/{action.name}")
    verb = "unlink" if getattr(record, "mode", None) == "link" else "remove"
    return f"{verb:<8} {target}{suffix}"


# -- status ----------------------------------------------------------------


def print_status(args, catalog: Catalog) -> int:
    harnesses = resolve_harnesses(args)
    everyone, scans = scan_all(catalog, args)
    if args.json:
        payload = {
            "toolkit": toolkit_version(catalog.repo).label,
            "harnesses": {
                harness.id: {
                    key: {
                        "status": str(record.status),
                        "mode": record.mode,
                        "installed_version": record.installed_version,
                        "source_version": _source_version(catalog, key),
                        "via": _via(harness, record, scans),
                    }
                    for key, record in scans[harness.id].items()
                }
                for harness in harnesses
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    keys = [item.key for item in list(catalog.skills) + list(catalog.agents) + list(catalog.commands)]
    for harness in harnesses:
        keys.extend(key for key in scans[harness.id] if key not in keys)
    print(f"PAMAGA Agent Toolkit {toolkit_version(catalog.repo).label}")
    for harness in harnesses:
        print(f"  {harness.label:<12} {harness.base}")
    print()
    width = max([len(key) for key in keys] + [4])
    rows = []
    printed: set = set()
    for key in keys:
        if key in printed:
            continue
        printed.add(key)
        records = [scans[harness.id].get(key) for harness in harnesses]
        if key.startswith("command/") and all(
            record is None or record.status == Status.NOT_INSTALLED for record in records
        ):
            continue  # wrappers nobody installed are noise
        cells = []
        for harness, record in zip(harnesses, records):
            via = _via(harness, record, scans) if record is not None else None
            if via is not None:
                provider = scans[via][key]
                cells.append(f"{STATUS_MARK[provider.status]} via {_label(everyone, via)}")
                continue
            if record is None or record.status == Status.NOT_INSTALLED:
                cells.append(f"{STATUS_MARK[Status.NOT_INSTALLED]} not installed")
                continue
            text = f"{STATUS_MARK[record.status]} {STATUS_WORDS[record.status]}"
            if record.mode:
                text += f" ({record.mode}"
                text += f", {record.installed_version})" if record.installed_version else ")"
            cells.append(text)
        rows.append((key, _source_version(catalog, key) or "-", cells))
    column = max([len(h.label) for h in harnesses]
                 + [len(cell) for _, _, cells in rows for cell in cells] + [1])
    print(("item".ljust(width) + "  " + "source".ljust(16)
           + "".join(f"  {h.label:<{column}}" for h in harnesses)).rstrip())
    for key, source, cells in rows:
        print((key.ljust(width) + "  " + source.ljust(16)
               + "".join(f"  {cell:<{column}}" for cell in cells)).rstrip())
    print()
    print("= linked  * up to date  ^ update available  ~ modified locally  "
          "! not installed by the toolkit  x no longer in the toolkit")
    return 0


def _via(harness: Harness, record: Installed, scans: Mapping[str, Mapping[str, Installed]]) -> Optional[str]:
    """Harness whose skills dir gives `harness` this skill, when it has no copy of its own."""
    if record.kind != "skill" or record.status not in (Status.NOT_INSTALLED, Status.ORPHANED):
        return None
    return shared_source(harness, record.name, scans)


def _source_version(catalog: Catalog, key: str) -> Optional[str]:
    if "/" not in key:
        return None
    kind, name = key.split("/", 1)
    item = catalog.get(kind, name)
    if item is None:
        return None
    return item_version_for(catalog)(item).label


# -- TUI entry -------------------------------------------------------------


def run_tui(args) -> int:
    """Run the interactive TUI; import it lazily so the CLI works without it."""
    try:
        from installer.tui.app import run
        from installer.tui.style import Style

        ctx = build_context(args)
    except Exception as exc:  # a broken TUI must not break the CLI
        print(f"error: cannot start the interactive installer: {exc}", file=sys.stderr)
        return 1
    style = Style.detect(no_color=args.no_color, ascii=args.ascii)
    return run(ctx, style)


def build_context(args):
    """The real `AppContext` for the TUI; see installer.tui.app.AppContext."""
    from installer.tui.app import AppContext

    offline = bool(args.offline or os.environ.get("PAMAGA_OFFLINE"))

    def make() -> AppContext:
        catalog = load_catalog(REPO)
        user_harnesses = all_harnesses("user")
        scans = {harness.id: scan(catalog, harness, Manifest.load(harness.base)) for harness in user_harnesses}

        def remote_release() -> Optional[str]:
            # Blocking on purpose: the app calls it once, in its own thread.
            if offline:
                return None
            return latest_remote_release(REPO)

        def remote_dev_commit() -> Optional[str]:
            if offline:
                return None
            return latest_remote_dev_commit(REPO)

        def guarded_pull_status():
            if offline:
                return False, "Offline mode: pull in a terminal."
            return pull_status(REPO)

        def harnesses_for(scope: str) -> List[Harness]:
            return all_harnesses(scope, project=Path.cwd())

        def scan_one(harness: Harness):
            return scan(catalog, harness, Manifest.load(harness.base))

        def version_of(item: Item) -> ItemVersion:
            relative = item.source.relative_to(REPO).as_posix()
            return versions.item_version(REPO, relative)

        def apply(actions, harnesses, on_progress=None):
            return apply_actions(
                actions, catalog, harnesses, now=datetime.now().astimezone(), on_progress=on_progress
            )

        def reload() -> AppContext:
            versions.clear_cache()
            return make()

        return AppContext(
            catalog=catalog,
            toolkit_version=toolkit_version(REPO),
            default_mode=default_mode(user_harnesses, scans),
            project=Path.cwd(),
            harnesses_for=harnesses_for,
            scan=scan_one,
            item_version=version_of,
            apply=apply,
            remote_release=remote_release,
            remote_dev_commit=remote_dev_commit,
            pull_status=guarded_pull_status,
            pull=lambda: pull(REPO),
            reload=reload,
        )

    return make()


if __name__ == "__main__":
    sys.exit(main())
