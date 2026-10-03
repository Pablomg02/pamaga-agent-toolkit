"""The interactive installer: screens, navigation and the main loop.

`App` holds all the state and does no I/O of its own: `handle(key)` reacts
to a key name, `tick()` advances animations and collects background work
(the remote release check, the install worker) and `render(width, height)`
returns exactly `height` lines, none wider than `width`. Tests drive it with
a fake `AppContext` and never touch a terminal; `run()` is the thin loop
that connects it to `terminal.Terminal`.

Screens: splash -> harnesses -> components (with details) -> review ->
install. Right (or `enter`) moves to the next step and left (or `esc`) back
to the previous one; on Review only `enter` applies, so an arrow key never
installs anything. `?` shows the keys, `q` quits (asking first when the
selection changed), `U` pulls the clone when that is safe.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from installer.actions import Action, Result, Selection, plan_actions
from installer.catalog import STAGE_ORDER, Catalog, Item
from installer.harnesses import Harness
from installer.state import Installed, Status
from installer.versions import ItemVersion, ToolkitVersion, channel_notice, release_key

from . import logo
from .style import THEME, Style, display_width, pad, stage_colour, wrap
from .widgets import box, key_hints, progress_bar, spinner

MIN_WIDTH = 60
MIN_HEIGHT = 18
DETAILS_MIN_WIDTH = 110
SPLIT_LOGO_WIDTH = 100
RED = "#f85149"
CURSOR_BG = "#30363d"
STEPS = ("Harnesses", "Components", "Review", "Install")
STEP_OF = {"harnesses": 0, "components": 1, "details": 1, "review": 2, "install": 3}

MANAGED = (Status.LINKED, Status.UP_TO_DATE, Status.OUTDATED, Status.MODIFIED)

STATUS_COLOUR = {
    Status.LINKED: "build",
    Status.UP_TO_DATE: "build",
    Status.OUTDATED: "check",
    Status.MODIFIED: "keep",
    Status.UNMANAGED: "check",
    Status.FOREIGN_LINK: "check",
    Status.ORPHANED: "muted",
    Status.NOT_INSTALLED: "muted",
}

STATUS_TEXT = {
    Status.LINKED: "linked to this clone",
    Status.UP_TO_DATE: "up to date",
    Status.OUTDATED: "update available",
    Status.MODIFIED: "modified locally",
    Status.UNMANAGED: "not installed by the toolkit",
    Status.FOREIGN_LINK: "not installed by the toolkit",
    Status.ORPHANED: "no longer in the toolkit",
    Status.NOT_INSTALLED: "not installed",
}

OP_STYLE = {
    "install": ("+", "install", "build"),
    "update": ("outdated", "update", "check"),
    "switch": ("linked", "switch", "check"),
    "remove": ("-", "remove", "red"),
    "skip": ("!", "skip", "check"),
    "keep": ("dot", "keep", "muted"),
}

HELP = (
    ("Everywhere", ""),
    ("up / down", "move the cursor (also j / k)"),
    ("space", "mark or unmark the line under the cursor"),
    ("right / enter", "next step"),
    ("left / esc", "previous step"),
    ("?", "this help"),
    ("q", "quit (asks when there are unsaved choices)"),
    ("U", "update this clone from its remote (git pull --ff-only)"),
    ("", ""),
    ("Components", ""),
    ("a", "mark all skills, or none when all are marked"),
    ("u", "mark every skill that has an update"),
    ("i", "full details of the skill under the cursor"),
    ("/", "filter by name or description"),
    ("", ""),
    ("Review", ""),
    ("enter", "apply the changes (the right arrow never does)"),
    ("space", "overwrite the highlighted item (a backup is kept)"),
    ("v", "show or hide unchanged items"),
)


def _colour(name: str) -> str:
    return RED if name == "red" else THEME.get(name, THEME["text"])


# Skill descriptions end with when the model should load them ("Use when the
# user says..."). People choosing what to install only need what it does.
TRIGGER_STARTS = (" Use when ", " Use only when ", " Load it ")


def what_it_does(description: str) -> str:
    """The part of a skill description that says what it does."""
    cut = min((i for i in (description.find(s) for s in TRIGGER_STARTS) if i > 0), default=len(description))
    return description[:cut].strip()


@dataclass
class AppContext:
    """Everything the app needs from outside, injectable for tests.

    `scan` returns the `state.scan` mapping for one harness, `apply` runs
    `actions.apply_actions` for the given harnesses with an optional
    `on_progress` callback and returns one `Result` per action, and `reload`
    re-reads the repository and returns a fresh context (used after a pull).
    """

    catalog: Catalog
    toolkit_version: ToolkitVersion
    default_mode: str
    project: Path
    harnesses_for: Callable[[str], List[Harness]]
    scan: Callable[[Harness], Dict[str, Installed]]
    item_version: Callable[[Item], ItemVersion]
    apply: Callable[..., List[Result]]
    remote_release: Callable[[], Optional[str]]
    pull_status: Callable[[], Tuple[bool, str]]
    pull: Callable[[], Tuple[bool, str]]
    reload: Callable[[], "AppContext"]
    remote_dev_commit: Callable[[], Optional[str]] = lambda: None


class App:
    """State machine of the installer UI; see the module docstring."""

    def __init__(self, ctx, style: Style) -> None:
        self.ctx = ctx
        self.style = style
        self.screen = "splash"
        self.done = False
        self.exit_code = 0
        self.notice = ""
        self.dialog: Optional[dict] = None
        self.show_help = False
        self.frame = 0
        self.started = time.monotonic()
        # Harnesses
        self.scope = "user"
        self.harness_cursor = 0
        self._load_harnesses()
        detected = [h.id for h in self.harnesses if h.detected()]
        self.checked = set(detected or [self.harnesses[0].id])
        # Components
        self.cursor = 0
        self.scroll = 0
        self.filter = ""
        self.filtering = False
        self.touched = False
        self.chosen: set = set()
        self.agents: set = set()
        self.commands = True
        self.mode = ctx.default_mode
        # Until the user changes the mode, installed items keep their own.
        self.mode_touched = False
        self._initial_selection()
        self.initial = self._selection_key()
        self.details_item: Optional[str] = None
        self.details_scroll = 0
        # Review
        self.force: set = set()
        self.show_unchanged = False
        self.review_cursor = 0
        self.review_scroll = 0
        self.actions: List[Action] = []
        self.candidates: set = set()
        # Install
        self.results: List[Result] = []
        self.progress = (0, 0)
        self.installing = False
        self.install_error = ""
        self._queue: "queue.Queue" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        # Remote release check
        self.remote: Optional[str] = None
        self.remote_dev: Optional[str] = None
        self._remote_thread: Optional[threading.Thread] = None
        self._remote_box: List[Optional[str]] = []

    # -- data ----------------------------------------------------------------

    def _load_harnesses(self) -> None:
        self.harnesses = list(self.ctx.harnesses_for(self.scope))
        self.scans: Dict[str, Dict[str, Installed]] = {h.id: self.ctx.scan(h) for h in self.harnesses}

    def _selected_harnesses(self):
        return [h for h in self.harnesses if h.id in self.checked]

    def _status(self, harness_id: str, key: str) -> Status:
        installed = self.scans.get(harness_id, {}).get(key)
        return installed.status if installed else Status.NOT_INSTALLED

    def _initial_selection(self) -> None:
        selected = {h.id for h in self._selected_harnesses()}
        installed = {
            i.name
            for hid, scanned in self.scans.items() if hid in selected
            for i in scanned.values() if i.kind == "skill" and i.status in MANAGED
        }
        known = {item.name for item in self.ctx.catalog.skills}
        self.chosen = (installed & known) or set(known)
        self.agents = {
            i.name
            for hid, scanned in self.scans.items() if hid in selected
            for i in scanned.values() if i.kind == "agent" and i.status in MANAGED
        } or {item.name for item in self.ctx.catalog.agents}
        modes = {
            i.mode
            for hid, scanned in self.scans.items() if hid in selected
            for i in scanned.values() if i.status in MANAGED and i.mode
        }
        self.mode = modes.pop() if len(modes) == 1 else self.ctx.default_mode
        commands_installed = [
            i for hid, scanned in self.scans.items() if hid in selected
            for i in scanned.values() if i.kind == "command" and i.status in MANAGED
        ]
        installed_any = bool(installed)
        self.commands = bool(commands_installed) or not installed_any

    def _has_installed(self) -> bool:
        return any(
            i.status in MANAGED
            for hid, scanned in self.scans.items() if hid in self.checked
            for i in scanned.values()
        )

    def _selection_key(self):
        return (frozenset(self.checked), frozenset(self.chosen), frozenset(self.agents),
                self.commands, self.mode)

    def _wanted(self) -> set:
        return self.ctx.catalog.required_closure(set(self.chosen))

    def _selection(self, force=None) -> Selection:
        return Selection(
            harness_ids=frozenset(self.checked),
            skills=frozenset(self.chosen),
            agents=frozenset(self.agents),
            commands=self.commands,
            mode=self.mode,
            prune=True,
            force=frozenset(self.force if force is None else force),
            keep_modes=not self.mode_touched,
        )

    def _plan(self, force=None) -> List[Action]:
        return plan_actions(self.ctx.catalog, self._selected_harnesses(), self.scans,
                            self._selection(force), self.ctx.item_version)

    def _update_target(self) -> Optional[str]:
        """What the U key would bring: a newer release, or newer commits on dev."""
        if self.ctx.toolkit_version.dev:
            commit = self.ctx.toolkit_version.commit
            if self.remote_dev and commit and not self.remote_dev.startswith(commit):
                return f"origin/dev {self.remote_dev[:7]}"
            return None
        tag = self.ctx.toolkit_version.tag
        if self.remote and (not tag or release_key(self.remote) > release_key(tag)):
            return self.remote
        return None

    def _update_available(self) -> bool:
        return self._update_target() is not None

    # -- input ---------------------------------------------------------------

    def handle(self, key: str) -> None:
        if key == "ctrl-c":
            self.done = True
            self.exit_code = 130
            return
        if self.dialog is not None:
            self._handle_dialog(key)
            return
        if self.show_help:
            self.show_help = False
            return
        if self.filtering:
            self._handle_filter(key)
            return
        self.notice = ""
        if key == "?":
            self.show_help = True
            return
        if key == "U" and not self.installing:
            self._open_pull_dialog()
            return
        if key == "q":
            self._quit()
            return
        handler = getattr(self, "_key_" + self.screen)
        handler(key)

    def _quit(self) -> None:
        if self.installing:
            self.notice = "Wait for the installation to finish."
            return
        if self.screen in ("components", "details", "review", "harnesses") and \
                self._selection_key() != self.initial:
            self.dialog = {"kind": "quit", "title": "Quit?",
                           "lines": ["Your choices have not been applied.", "Quit anyway?"],
                           "hints": (("enter", "quit"), ("esc", "stay"))}
            return
        self.done = True

    def _handle_dialog(self, key: str) -> None:
        dialog = self.dialog
        if key in ("esc", "n"):
            self.dialog = None
            return
        if key not in ("enter", "y"):
            return
        self.dialog = None
        if dialog["kind"] == "quit":
            self.done = True
        elif dialog["kind"] == "pull" and dialog.get("can"):
            self._do_pull()

    def _open_pull_dialog(self) -> None:
        can, reason = self.ctx.pull_status()
        lines = [reason]
        if self.ctx.toolkit_version.dev:
            lines = channel_notice(self.ctx.toolkit_version, self.remote, self.remote_dev) + lines
        elif self.remote:
            lines.insert(0, f"Newest release: {self.remote} (you have {self.ctx.toolkit_version.label}).")
        if can:
            lines.append("Run git pull --ff-only now?")
            hints = (("enter", "pull"), ("esc", "cancel"))
        else:
            hints = (("esc", "close"),)
        self.dialog = {"kind": "pull", "can": can, "title": "Update the clone", "lines": lines,
                       "hints": hints}

    def _do_pull(self) -> None:
        ok, output = self.ctx.pull()
        if not ok:
            self.notice = output.splitlines()[0] if output else "git pull failed."
            return
        self.ctx = self.ctx.reload()
        known = {item.name for item in self.ctx.catalog.skills}
        self.chosen &= known
        self.agents &= {item.name for item in self.ctx.catalog.agents}
        self._load_harnesses()
        self.remote = None
        self.remote_dev = None
        self.notice = f"Clone updated to {self.ctx.toolkit_version.label}; press u to select updates."

    def _handle_filter(self, key: str) -> None:
        if key == "esc":
            self.filter = ""
            self.filtering = False
        elif key == "enter":
            self.filtering = False
        elif key == "backspace":
            self.filter = self.filter[:-1]
        elif key == "space":
            self.filter += " "
        elif len(key) == 1:
            self.filter += key
        self.cursor = 0
        self.scroll = 0
        rows = self._selectable(self._component_rows())
        self.cursor = rows[0] if rows else 0

    # splash

    def _key_splash(self, key: str) -> None:
        if key in ("enter", "space", "right"):
            self.screen = "harnesses"

    # harnesses

    def _key_harnesses(self, key: str) -> None:
        count = len(self.harnesses)
        if key in ("up", "k"):
            self.harness_cursor = (self.harness_cursor - 1) % count
        elif key in ("down", "j", "tab"):
            self.harness_cursor = (self.harness_cursor + 1) % count
        elif key == "space":
            hid = self.harnesses[self.harness_cursor].id
            self.checked ^= {hid}
        elif key == "s":
            self.scope = "project" if self.scope == "user" else "user"
            self._load_harnesses()
            self.checked = {h.id for h in self.harnesses if h.id in self.checked} or \
                {self.harnesses[0].id}
            if not self.touched:
                self._initial_selection()
                self.initial = self._selection_key()
        elif key in ("enter", "right"):
            if not self.checked:
                self.notice = "Mark at least one harness with space."
                return
            if not self.touched:
                self._initial_selection()
                self.initial = self._selection_key()
            self.screen = "components"
            rows = self._selectable(self._component_rows())
            if self.cursor not in rows:
                self.cursor = rows[0] if rows else 0
        elif key in ("esc", "left"):
            self.screen = "splash"

    # components

    def _component_rows(self) -> List[Tuple[str, str]]:
        catalog = self.ctx.catalog
        text = self.filter.lower()
        rows: List[Tuple[str, str]] = []
        for stage in STAGE_ORDER:
            skills = [
                s for s in catalog.skills
                if s.stage == stage and (not text or text in s.name.lower()
                                         or text in s.description.lower())
            ]
            if skills:
                rows.append(("group", stage))
                rows.extend(("skill", s.name) for s in skills)
        if not rows:
            rows.append(("info", f"No skill matches \"{self.filter}\""))
        rows.append(("group", "options"))
        if any(h.supports_commands for h in self._selected_harnesses()):
            rows.append(("option", "commands"))
        rows.append(("option", "mode"))
        rows.extend(("agent", a.name) for a in catalog.agents)
        return rows

    @staticmethod
    def _selectable(rows) -> List[int]:
        return [i for i, (kind, _) in enumerate(rows) if kind in ("skill", "option", "agent")]

    def _move(self, rows, delta: int) -> None:
        selectable = self._selectable(rows)
        if not selectable:
            return
        if self.cursor not in selectable:
            self.cursor = selectable[0]
            return
        index = selectable.index(self.cursor)
        index = max(0, min(len(selectable) - 1, index + delta))
        self.cursor = selectable[index]

    def _current(self) -> Tuple[str, str]:
        rows = self._component_rows()
        if 0 <= self.cursor < len(rows):
            return rows[self.cursor]
        return ("info", "")

    def _key_components(self, key: str) -> None:
        rows = self._component_rows()
        if self.cursor not in self._selectable(rows):
            self._move(rows, 0)
        kind, name = self._current()
        if key in ("up", "k"):
            self._move(rows, -1)
        elif key in ("down", "j"):
            self._move(rows, 1)
        elif key == "pgup":
            self._move(rows, -10)
        elif key == "pgdn":
            self._move(rows, 10)
        elif key == "home":
            self._move(rows, -len(rows))
        elif key == "end":
            self._move(rows, len(rows))
        elif key == "space":
            self._toggle(kind, name)
        elif key == "a":
            every = {s.name for s in self.ctx.catalog.skills}
            self.chosen = set() if self._wanted() >= every else every
            self.touched = True
        elif key == "n":
            self.chosen = set()
            self.touched = True
        elif key == "u":
            outdated = self._outdated()
            if outdated:
                self.chosen |= outdated
                self.touched = True
                self.notice = f"Selected {len(outdated)} skill(s) with updates."
            else:
                self.notice = "No updates: every installed skill is current."
        elif key == "/":
            self.filtering = True
        elif key == "i" and kind == "skill":
            self.details_item = name
            self.details_scroll = 0
            self.screen = "details"
        elif key in ("enter", "right"):
            self._open_review()
        elif key == "esc" and self.filter:
            self.filter = ""
        elif key in ("esc", "left"):
            self.screen = "harnesses"

    def _outdated(self) -> set:
        return {
            s.name for s in self.ctx.catalog.skills
            if any(self._status(h.id, s.key) == Status.OUTDATED for h in self._selected_harnesses())
        }

    def _toggle(self, kind: str, name: str) -> None:
        self.touched = True
        if kind == "option" and name == "mode":
            self.mode = "copy" if self.mode == "link" else "link"
            self.mode_touched = True
        elif kind == "option" and name == "commands":
            self.commands = not self.commands
        elif kind == "agent":
            self.agents ^= {name}
        elif kind == "skill":
            wanted = self._wanted()
            if name in wanted:
                remaining = self.ctx.catalog.required_closure(self.chosen - {name})
                if name in remaining:
                    by = [d for d in self.ctx.catalog.dependents(name) if d in remaining]
                    self.notice = f"{name} is required by {', '.join(by)}."
                    return
                self.chosen.discard(name)
            else:
                self.chosen.add(name)

    # details

    def _key_details(self, key: str) -> None:
        if key in ("esc", "left", "i", "enter"):
            self.screen = "components"
        elif key in ("down", "j"):
            self.details_scroll += 1
        elif key in ("up", "k"):
            self.details_scroll = max(0, self.details_scroll - 1)
        elif key == "pgdn":
            self.details_scroll += 10
        elif key == "pgup":
            self.details_scroll = max(0, self.details_scroll - 10)
        elif key == "home":
            self.details_scroll = 0
        elif key == "space":
            self._toggle("skill", self.details_item or "")

    # review

    def _open_review(self) -> None:
        base = self._plan(force=set())
        scans = self.scans
        self.candidates = set()
        for action in base:
            key = f"{action.harness_id}:{action.kind}/{action.name}"
            status = scans.get(action.harness_id, {}).get(f"{action.kind}/{action.name}")
            if action.op == "skip" or (action.op == "keep" and status is not None
                                       and status.status == Status.MODIFIED
                                       and action.reason == "no longer selected"):
                self.candidates.add(key)
        self.force &= self.candidates
        self.actions = self._plan()
        self.review_cursor = 0
        self.review_scroll = 0
        self.screen = "review"

    def _review_rows(self) -> List[Tuple[str, object]]:
        rows: List[Tuple[str, object]] = []
        for harness in self._selected_harnesses():
            own = [a for a in self.actions if a.harness_id == harness.id]
            visible = [a for a in own if a.op != "keep" or self.show_unchanged
                       or self._candidate_key(a) in self.candidates]
            rows.append(("harness", harness))
            if not visible:
                rows.append(("info", "nothing to change"))
            rows.extend(("action", a) for a in visible)
        return rows

    @staticmethod
    def _candidate_key(action: Action) -> str:
        return f"{action.harness_id}:{action.kind}/{action.name}"

    def _changes(self) -> List[Action]:
        return [a for a in self.actions if a.op not in ("keep", "skip")]

    def _key_review(self, key: str) -> None:
        rows = self._review_rows()
        selectable = [i for i, (kind, _) in enumerate(rows) if kind == "action"]
        if selectable and self.review_cursor not in selectable:
            self.review_cursor = selectable[0]
        if key in ("up", "k", "down", "j", "pgup", "pgdn", "home", "end") and selectable:
            delta = {"up": -1, "k": -1, "down": 1, "j": 1, "pgup": -10, "pgdn": 10,
                     "home": -len(rows), "end": len(rows)}[key]
            index = selectable.index(self.review_cursor)
            self.review_cursor = selectable[max(0, min(len(selectable) - 1, index + delta))]
        elif key == "space" and selectable:
            action = rows[self.review_cursor][1]
            fkey = self._candidate_key(action)
            if fkey in self.candidates:
                self.force ^= {fkey}
                self.touched = True
                self.actions = self._plan()
            else:
                self.notice = "Only items that need overwriting can be toggled here."
        elif key == "v":
            self.show_unchanged = not self.show_unchanged
        elif key == "enter":
            if not self._changes():
                self.done = True
                return
            self._start_install()
        elif key in ("esc", "left"):
            self.screen = "components"

    # install

    def _start_install(self) -> None:
        self.screen = "install"
        self.installing = True
        self.results = []
        actions = list(self.actions)
        self.progress = (0, len(actions))
        harnesses = self._selected_harnesses()

        def on_progress(done: int, total: int, result: Result) -> None:
            self._queue.put(("progress", done, total, result))

        def work() -> None:
            try:
                results = self.ctx.apply(actions, harnesses, on_progress)
                self._queue.put(("done", results))
            except Exception as exc:  # the UI must survive any engine bug
                self._queue.put(("error", str(exc) or exc.__class__.__name__))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _key_install(self, key: str) -> None:
        if self.installing:
            return
        if key in ("enter", "esc"):
            self.done = True

    def _finish_install(self) -> None:
        self.installing = False
        failed = [r for r in self.results if not r.ok]
        self.exit_code = 1 if failed or self.install_error else 0
        self.initial = self._selection_key()
        self._load_harnesses()

    # -- background ----------------------------------------------------------

    def tick(self) -> None:
        self.frame += 1
        if self._remote_thread is None:
            def check() -> None:
                try:
                    if self.ctx.toolkit_version.dev:
                        self.remote_dev = self.ctx.remote_dev_commit()
                    self._remote_box.append(self.ctx.remote_release())
                except Exception:
                    self._remote_box.append(None)
            self._remote_thread = threading.Thread(target=check, daemon=True)
            self._remote_thread.start()
        elif self._remote_box and self.remote is None and not getattr(self, "_remote_seen", False):
            self._remote_seen = True
            self.remote = self._remote_box[0]
        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break
            if message[0] == "progress":
                _, done, total, result = message
                self.progress = (done, total)
                self.results.append(result)
            elif message[0] == "done":
                self.results = list(message[1])
                self.progress = (len(self.results), len(self.results))
                self._finish_install()
            elif message[0] == "error":
                self.install_error = message[1]
                self._finish_install()

    # -- rendering -----------------------------------------------------------

    def render(self, width: int, height: int) -> List[str]:
        style = self.style
        if width <= 0 or height <= 0:
            return []
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            message = f"Terminal too small {self._dash()} resize to at least {MIN_WIDTH}x{MIN_HEIGHT}"
            lines = [""] * height
            text = style.truncate(message, width)
            lines[height // 2] = " " * max(0, (width - display_width(text)) // 2) + text
            return self._fit(lines, width, height)
        if self.screen == "splash":
            header: List[str] = []
        else:
            header = [self._header(width), self._stepper(width)]
        footer = self._footer(width)
        body_height = max(0, height - len(header) - len(footer))
        body = getattr(self, "_render_" + self.screen)(width, body_height)
        body = (list(body) + [""] * body_height)[:body_height]
        if self.dialog is not None:
            body = self._overlay(body, self._dialog_box(width), width)
        elif self.show_help:
            body = self._overlay(body, self._help_box(width, body_height), width)
        return self._fit(header + body + footer, width, height)

    def _fit(self, lines: Sequence[str], width: int, height: int) -> List[str]:
        lines = (list(lines) + [""] * height)[:height]
        return [self.style.fit(line, width) for line in lines]

    def _dash(self) -> str:
        return "—" if self.style.unicode else "-"

    def _header(self, width: int) -> str:
        style = self.style
        left = " " + style.bold("PAMAGA Agent Toolkit")
        if self.scope == "project":
            left += style.fg(f"  project: {self.ctx.project}", THEME["muted"])
        right = self.ctx.toolkit_version.label
        if self.ctx.toolkit_version.dev:
            right += " " + style.bold(style.fg("[dev]", THEME["check"]))
        if self._update_available():
            right += f" {style.glyph('dot')} " + style.fg(f"{style.glyph('outdated')} {self._update_target()} (U)",
                                                         THEME["check"])
        right += " "
        gap = width - display_width(left) - display_width(right)
        if gap < 1:
            return style.truncate(left, width)
        return left + " " * gap + right

    def _stepper(self, width: int) -> str:
        style = self.style
        current = STEP_OF.get(self.screen, -1)
        parts = []
        for index, name in enumerate(STEPS):
            text = f"{index + 1} {name}"
            if index == current:
                text = style.bold(style.fg(text, THEME["think"]))
            elif index < current:
                text = style.fg(text, THEME["text"])
            else:
                text = style.fg(text, THEME["muted"])
            parts.append(text)
        return " " + f" {style.fg(style.glyph('gt'), THEME['line'])} ".join(parts)

    def _footer(self, width: int) -> List[str]:
        """A rule, one line saying what to do here, and the keys."""
        style = self.style
        lines = [style.fg(style.glyph("hline") * width, THEME["line"])]
        if self.notice:
            lines.append(" " + style.fg(style.truncate(self.notice, width - 1), THEME["check"]))
        elif self.filtering or self.filter:
            cursor = "_" if self.filtering else ""
            lines.append(" " + style.fg(f"filter: {self.filter}{cursor}", THEME["think"]))
        else:
            instruction = self._instruction()
            if instruction:
                lines.append(" " + style.truncate(instruction, width - 1))
        lines += [" " + line for line in key_hints(self._hints(width), width - 1, style)]
        return lines

    def _instruction(self) -> str:
        if self.dialog is not None:
            return ""
        screen = self.screen
        mark = self.style.glyph("checkbox_on")
        if screen == "harnesses":
            return f"Press space to mark ({mark}) each harness to install into, then {self._key('right')} to continue."
        if screen == "components":
            return f"Space marks ({mark}) a skill to install; unmarking an installed one removes it."
        if screen == "details":
            return f"Press space to mark or unmark this skill, {self._key('left')} to go back."
        if screen == "review":
            if not self._changes():
                return "Nothing to change."
            return "Nothing is changed until you press enter."
        if screen == "install" and not self.installing:
            return "Finished. Press enter to exit."
        return ""

    def _key(self, name: str) -> str:
        return self.style.glyph("key_" + name)

    def _hints(self, width: int = 0) -> List[Tuple[str, str]]:
        if self.dialog is not None:
            return list(self.dialog["hints"])
        if self.filtering:
            return [("type", "to filter"), ("enter", "keep"), ("esc", "clear")]
        screen = self.screen
        updown = self._key("up") + self._key("down") if self.style.unicode else "up/down"
        right, left = self._key("right"), self._key("left")
        if screen == "splash":
            return [(right, "start"), ("?", "help"), ("q", "quit")]
        if screen == "harnesses":
            return [(updown, "move"), ("space", "mark"), (right, "next"), (left, "back"),
                    ("s", f"install into the {'user' if self.scope == 'project' else 'project'} instead"),
                    ("q", "quit")]
        if screen == "components":
            hints = [(updown, "move"), ("space", "mark"), ("a", "all/none")]
            if self._outdated():
                hints.append(("u", "mark updates"))
            if width < DETAILS_MIN_WIDTH:
                hints.append(("i", "details"))
            return hints + [(right, "review"), (left, "back"), ("?", "more keys")]
        if screen == "details":
            return [(updown, "scroll"), ("space", "mark"), (left, "back")]
        if screen == "review":
            hints = [("enter", "apply" if self._changes() else "exit")]
            if self.candidates:
                hints.append(("space", "overwrite"))
            return hints + [("v", "show unchanged"), (left, "back")]
        if screen == "install":
            if self.installing:
                return [("", "installing...")]
            return [("enter", "exit")]
        return []

    # splash

    def _render_splash(self, width: int, height: int) -> List[str]:
        style = self.style
        blink = (time.monotonic() - self.started) % 4.0 < 0.15
        mascot = logo.render_logo(style, blink=blink)
        mark = logo.render_wordmark(style, width - 4)
        info = [
            style.italic(style.fg(logo.TAGLINE, THEME["muted"])),
            "",
            "Version " + style.bold(self.ctx.toolkit_version.label),
        ]
        if self.ctx.toolkit_version.dev:
            info.append(style.fg("Development build: the stable release comes from main"
                                 + (f" ({self.remote})." if self.remote else "."), THEME["check"]))
        if self._update_available():
            info.append(style.fg(f"{style.glyph('outdated')} {self._update_target()} available "
                                 f"{self._dash()} press U to update the clone", THEME["check"]))
        info.append("")
        for harness in self.harnesses:
            info.append(self._harness_summary_line(harness))
        candidates = []
        if width >= SPLIT_LOGO_WIDTH:
            right = mark + [""] + info
            mascot_width = max(display_width(line) for line in mascot)
            side = []
            for index in range(max(len(mascot), len(right))):
                left = mascot[index] if index < len(mascot) else ""
                other = right[index] if index < len(right) else ""
                side.append(pad(left, mascot_width) + "    " + other)
            candidates.append(side)
        candidates.append(mascot + [""] + mark + [""] + info)
        candidates.append(mark + [""] + info)
        candidates.append([style.bold("PAMAGA AGENT TOOLKIT")] + info)
        for lines in candidates:
            if len(lines) <= height - 1 and all(display_width(l) <= width - 2 for l in lines):
                break
        block_width = max(display_width(line) for line in lines)
        left = max(0, (width - block_width) // 2)
        top = max(0, (height - len(lines)) // 2)
        return [""] * top + [" " * left + line for line in lines]

    def _harness_summary_line(self, harness) -> str:
        style = self.style
        found = harness.detected()
        mark = style.fg(style.glyph("ok"), THEME["build"]) + " detected" if found else \
            style.fg("not found", THEME["muted"])
        return f"{pad(harness.label, 12)} {mark} {style.glyph('dot')} {self._counts(harness.id)}"

    def _counts(self, harness_id: str) -> str:
        scanned = self.scans.get(harness_id, {})
        installed = sum(1 for i in scanned.values() if i.kind == "skill" and i.status in MANAGED)
        updates = sum(1 for i in scanned.values() if i.kind == "skill" and i.status == Status.OUTDATED)
        modified = sum(1 for i in scanned.values() if i.kind == "skill" and i.status == Status.MODIFIED)
        parts = [f"{installed} installed"]
        if updates:
            parts.append(self.style.fg(f"{updates} update{'s' if updates != 1 else ''}", THEME["check"]))
        if modified:
            parts.append(self.style.fg(f"{modified} modified", THEME["keep"]))
        return f" {self.style.glyph('dot')} ".join(parts)

    # harnesses

    def _render_harnesses(self, width: int, height: int) -> List[str]:
        style = self.style
        lines = ["", " Where should the toolkit be installed?"
                 + style.fg(f"  (scope: {self.scope})", THEME["muted"]), ""]
        for index, harness in enumerate(self.harnesses):
            on = harness.id in self.checked
            check = style.glyph("checkbox_on" if on else "checkbox_off")
            check = style.fg(check, THEME["build"]) if on else style.fg(check, THEME["muted"])
            found = style.fg("detected", THEME["build"]) if harness.detected() else \
                style.fg("not found", THEME["muted"])
            arrow = style.glyph("arrow") if index == self.harness_cursor else " "
            row = f" {arrow} {check} {pad(style.bold(harness.label), 12)} {pad(found, 10)} " + \
                style.fg(str(harness.base), THEME["muted"])
            lines.append(self._cursor_line(row, width, index == self.harness_cursor))
            lines.append("       " + self._counts(harness.id))
            lines.append("")
        lines.append(style.fg(" Detected harnesses are preselected. Press s to install into "
                              "the current project instead.", THEME["muted"]))
        return lines

    def _cursor_line(self, text: str, width: int, active: bool) -> str:
        if not active:
            return text
        style = self.style
        text = style.fit(text, width)
        if style.depth in ("truecolor", "256"):
            return style.bg(text, CURSOR_BG)
        if style.depth == "16":
            return style.reverse(text)
        return text

    # components

    def _render_components(self, width: int, height: int) -> List[str]:
        show_details = width >= DETAILS_MIN_WIDTH
        right_width = max(38, width * 2 // 5) if show_details else 0
        left_width = width - right_width
        inner = max(0, left_width - 4)
        box_height = max(3, height)
        list_lines = self._component_lines(inner, box_height - 2)
        list_lines = (list_lines + [""] * box_height)[: box_height - 2]  # boxes fill the screen
        title = f"Skills {self.style.glyph('dot')} {len(self._wanted())} of {len(self.ctx.catalog.skills)} marked"
        left = box(title, list_lines, left_width, THEME["line"], self.style)
        if not show_details:
            return left
        kind, name = self._current()
        item = self.ctx.catalog.get("skill", name) if kind == "skill" else None
        if item is not None:
            detail = self._details_lines(item, right_width - 4)[: box_height - 2]
            detail = (detail + [""] * box_height)[: box_height - 2]
            colour = stage_colour(item.stage)
            right = box(item.name, detail, right_width, colour, self.style)
        else:
            detail = self._option_help(kind, name, right_width - 4)
            detail = (detail + [""] * box_height)[: box_height - 2]
            right = box("Options", detail, right_width, THEME["line"], self.style)
        right = (right + [""] * len(left))[: len(left)]
        return [pad(l, left_width) + r for l, r in zip(left, right)]

    def _option_help(self, kind: str, name: str, width: int) -> List[str]:
        if kind == "option" and name == "mode":
            text = ("Space switches between link and copy.\n\n"
                    "link: symlinks to this clone, so a git pull updates every harness at once.\n\n"
                    "copy: real files, independent of the clone; the installer tracks their "
                    "version and offers updates.")
        elif kind == "option" and name == "commands":
            text = ("Space turns it on or off. Command wrappers let you type /<skill> in opencode. "
                    "Claude Code registers "
                    "skills as commands on its own, so it never gets them.")
        elif kind == "agent":
            agent = self.ctx.catalog.get("agent", name)
            text = agent.description if agent else ""
        else:
            text = ""
        return wrap(text, max(1, width))

    def _component_lines(self, width: int, height: int) -> List[str]:
        style = self.style
        rows = self._component_rows()
        name_width = max([len(s.name) for s in self.ctx.catalog.skills] + [10])
        fate_width = 20
        tag_width = max(0, width - 4 - name_width - 2 - fate_width - 1)
        wanted = self._wanted()
        lines = []
        first_group = True
        cursor_line = 0  # rows and lines differ: the SETTINGS header takes two lines
        for index, (kind, name) in enumerate(rows):
            active = index == self.cursor
            if active:
                cursor_line = len(lines)
            arrow = style.glyph("arrow") if active else " "
            if kind == "group":
                if name == "options":
                    lines.append("")
                    lines.append(style.bold(style.fg("SETTINGS", THEME["muted"])))
                    continue
                label = style.bold(style.fg(name.upper(), stage_colour(name)))
                if first_group:
                    head = style.fg(pad("on apply", fate_width), THEME["muted"])
                    label += " " * max(1, width - display_width(label) - fate_width) + head
                    first_group = False
                lines.append(label)
            elif kind == "skill":
                item = self.ctx.catalog.get("skill", name)
                on = name in wanted
                check = style.glyph("checkbox_on" if on else "checkbox_off")
                check = style.fg(check, stage_colour(item.stage)) if on else style.fg(check, THEME["muted"])
                if item.stage == "support" or not item.tagline:
                    count = len(self.ctx.catalog.dependents(name))
                    tagline = f"required by {count}" if count else item.description
                else:
                    tagline = item.tagline
                fate, colour = self._fate(item, on)
                text = (f"{arrow} {check} " + pad(style.fg(name, stage_colour(item.stage)), name_width)
                        + "  " + style.fit(style.fg(tagline, THEME["muted"]), tag_width) + " "
                        + style.fit(style.fg(fate, _colour(colour)), fate_width))
                lines.append(self._cursor_line(text, width, active))
            elif kind == "option" and name == "commands":
                check = style.glyph("checkbox_on" if self.commands else "checkbox_off")
                text = f"{arrow} {check} Add /commands for opencode"
                lines.append(self._cursor_line(text, width, active))
            elif kind == "option" and name == "mode":
                choices = []
                for mode in ("link", "copy"):
                    radio = style.glyph("radio_on" if self.mode == mode else "radio_off")
                    choice = f"{radio} {mode}"
                    choices.append(style.bold(choice) if self.mode == mode else style.fg(choice, THEME["muted"]))
                note = "symlinks that follow this clone" if self.mode == "link" else \
                    "independent copies of the files"
                if not self.mode_touched and self._has_installed():
                    note = "only for new skills"
                text = f"{arrow}   Install as  {'  '.join(choices)}   " + style.fg(note, THEME["muted"])
                lines.append(self._cursor_line(text, width, active))
            elif kind == "agent":
                on = name in self.agents
                check = style.glyph("checkbox_on" if on else "checkbox_off")
                text = f"{arrow} {check} agent {name}"
                lines.append(self._cursor_line(text, width, active))
            else:
                lines.append(style.fg("    " + name, THEME["muted"]))
        # Keep the cursor visible.
        if height <= 0:
            return []
        if cursor_line < self.scroll:
            self.scroll = max(0, cursor_line - 1)
        elif cursor_line >= self.scroll + height:
            self.scroll = cursor_line - height + 1
        self.scroll = max(0, min(self.scroll, max(0, len(lines) - height)))
        return lines[self.scroll:self.scroll + height]

    def _fate(self, item: Item, on: bool) -> Tuple[str, str]:
        """What applying does to a skill, in words, and the colour to say it in."""
        style = self.style
        harnesses = self._selected_harnesses()
        statuses = [self._status(h.id, item.key) for h in harnesses]
        managed = [s in MANAGED for s in statuses]
        if not on:
            # Same rule as _plan_unwanted: a hand-made identical copy is kept.
            scanned = [self.scans.get(h.id, {}).get(item.key) for h in harnesses]
            if any(i is not None and i.status in (Status.LINKED, Status.UP_TO_DATE, Status.OUTDATED)
                   and not (i.status == Status.UP_TO_DATE and not i.managed) for i in scanned):
                return f"{'−' if style.unicode else '-'} remove", "red"
            return "", "muted"
        if Status.OUTDATED in statuses:
            return f"{style.glyph('outdated')} update", "check"
        if Status.MODIFIED in statuses:
            return f"{style.glyph('modified')} edited, see review", "keep"
        if any(s in (Status.UNMANAGED, Status.FOREIGN_LINK) for s in statuses):
            return "! not ours, see review", "check"
        if all(managed):
            return f"{style.glyph('ok')} installed", "build"
        if any(managed):
            missing = [h.id for h, m in zip(harnesses, managed) if not m]
            return "+ install in " + ", ".join(missing), "build"
        return "+ install", "build"

    def _status_cell(self, harness_id: str, key: str) -> str:
        status = self._status(harness_id, key)
        name = status.value.replace("-", "_")
        return self.style.fg(self.style.glyph(name), _colour(STATUS_COLOUR[status]))

    def _details_lines(self, item: Item, width: int) -> List[str]:
        style = self.style
        width = max(10, width)
        lines: List[str] = []
        if item.tagline:
            lines.append(style.fg(item.tagline, stage_colour(item.stage)))
        lines.extend(wrap(what_it_does(item.description), width))
        lines.append("")
        version = self.ctx.item_version(item)

        def field(label: str, value: str) -> None:
            wrapped = wrap(value, max(1, width - 10)) or [""]
            lines.append(style.fg(pad(label, 10), THEME["muted"]) + wrapped[0])
            lines.extend(" " * 10 + rest for rest in wrapped[1:])

        field("Version", version.label)
        if version.date:
            field("Changed", f"{version.date} {version.subject or ''}".strip())
        command = f"/{item.name}" if item.user_invocable else "none (support skill)"
        field("Command", command)
        field("Requires", ", ".join(item.requires) or "nothing")
        dependents = self.ctx.catalog.dependents(item.name)
        if dependents:
            field("Needed by", ", ".join(dependents))
        for harness in self._selected_harnesses():
            installed = self.scans.get(harness.id, {}).get(item.key)
            status = installed.status if installed else Status.NOT_INSTALLED
            text = STATUS_TEXT[status]
            if status == Status.OUTDATED:
                text = f"update {installed.installed_version or '?'} {style.glyph('gt')} {version.label}"
            elif installed is not None and installed.installed_version and status in MANAGED:
                text += f" ({installed.installed_version})"
            badge = self._status_cell(harness.id, item.key)
            field(harness.id, f"{badge} {text}")
            if installed is not None:
                for change in installed.changed_files[:12]:
                    lines.append(" " * 12 + style.fg(change, THEME["muted"]))
        field("Files", ", ".join(item.files))
        body = self._skill_body(item)
        if body:
            lines.append("")
            lines.append(style.fg(style.glyph("hline") * width, THEME["line"]))
            for raw in body.splitlines():
                stripped = raw.strip()
                if stripped.startswith("#"):
                    lines.append(style.bold(stripped.lstrip("#").strip()))
                else:
                    lines.extend(wrap(raw, width) or [""])
        return lines

    @staticmethod
    def _skill_body(item: Item) -> str:
        try:
            text = (item.source / "SKILL.md").read_text(encoding="utf-8")
        except OSError:
            return ""
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                text = text[end + 4:]
        return text.strip()

    # details

    def _render_details(self, width: int, height: int) -> List[str]:
        item = self.ctx.catalog.get("skill", self.details_item or "")
        if item is None:
            return []
        lines = self._details_lines(item, width - 4)
        visible = max(0, height - 2)
        self.details_scroll = max(0, min(self.details_scroll, max(0, len(lines) - visible)))
        selected = "selected" if item.name in self._wanted() else "not selected"
        title = f"{item.name} {self.style.glyph('dot')} {selected}"
        return box(title, lines[self.details_scroll:self.details_scroll + visible], width,
                   stage_colour(item.stage), self.style)

    # review

    def _render_review(self, width: int, height: int) -> List[str]:
        style = self.style
        rows = self._review_rows()
        changes = self._changes()
        lines: List[str] = []
        if not changes:
            lines.append(style.fg(f"{style.glyph('ok')} Everything is up to date. "
                                  "Press enter to exit.", THEME["build"]))
        else:
            counts: Dict[str, int] = {}
            for action in changes:
                counts[action.op] = counts.get(action.op, 0) + 1
            summary = ", ".join(f"{n} to {op}" for op, n in sorted(counts.items()))
            lines.append(style.bold(f"{len(changes)} change(s): ") + summary)
        skills_in = {a.harness_id for a in self.actions if a.kind == "skill" and a.op != "remove"}
        if {"opencode", "claude"} <= skills_in:
            lines.append(style.fg("opencode also reads ~/.claude/skills; keep skill names distinct "
                                  "or install only the harnesses you use.", THEME["muted"]))
        lines.append("")
        header_count = len(lines)
        body = []
        for index, (kind, value) in enumerate(rows):
            if kind == "harness":
                body.append(style.bold(value.label) + style.fg(f" {style.glyph('arrow')} {value.base}",
                                                               THEME["muted"]))
            elif kind == "info":
                body.append(style.fg("   " + value, THEME["muted"]))
            else:
                body.append(self._cursor_line(self._action_line(value, index == self.review_cursor),
                                              width, index == self.review_cursor))
        visible = max(1, height - header_count)
        if self.review_cursor < self.review_scroll:
            self.review_scroll = max(0, self.review_cursor - 1)
        elif self.review_cursor >= self.review_scroll + visible:
            self.review_scroll = self.review_cursor - visible + 1
        return lines + body[self.review_scroll:self.review_scroll + visible]

    def _action_line(self, action: Action, active: bool) -> str:
        style = self.style
        glyph_name, verb, colour = OP_STYLE[action.op]
        mark = glyph_name if len(glyph_name) == 1 else style.glyph(glyph_name)
        if action.op == "remove" and style.unicode:
            mark = "−"
        arrow = style.glyph("arrow") if active else " "
        label = style.fg(f"{mark} {verb:<7}", _colour(colour))
        name = f"{action.kind} {action.name}"
        detail = ""
        if action.op == "update":
            detail = f"{action.from_version or '?'} {style.glyph('gt')} {action.to_version}"
        elif action.op in ("install", "switch") and action.mode:
            detail = action.mode
        if action.op == "skip" or action.backup or action.reason not in ("not installed",):
            reason = action.reason
            detail = f"{detail}  {reason}" if detail else reason
        fkey = self._candidate_key(action)
        if fkey in self.candidates:
            on = fkey in self.force
            box_glyph = style.glyph("checkbox_on" if on else "checkbox_off")
            detail = f"{box_glyph} overwrite (backup kept)  " + style.fg(detail, THEME["muted"])
        else:
            detail = style.fg(detail, THEME["muted"])
        return f" {arrow} {label} {pad(name, 28)} {detail}"

    # install

    def _render_install(self, width: int, height: int) -> List[str]:
        style = self.style
        done, total = self.progress
        bar_width = max(10, min(60, width - 20))
        lines = [""]
        state = style.fg(spinner(self.frame, style), THEME["think"]) if self.installing else \
            style.fg(style.glyph("ok"), THEME["build"])
        lines.append(f" {state} " + progress_bar(done, total, bar_width, style) + f" {done}/{total}")
        lines.append("")
        result_lines = []
        for result in self.results:
            action = result.action
            ok = style.fg(style.glyph("ok"), THEME["build"]) if result.ok else style.fg(style.glyph("fail"), RED)
            text = f"   {ok} {action.op:<7} {action.harness_id}: {action.kind} {action.name}"
            if not result.ok:
                text += style.fg(f"  {result.message}", RED)
            elif action.op not in ("keep",):
                text += style.fg(f"  {result.message}", THEME["muted"])
            if action.op != "keep":
                result_lines.append(text)
        summary: List[str] = []
        if not self.installing:
            summary = self._summary_lines()
        room = max(0, height - len(lines) - len(summary))
        lines += result_lines[-room:] if room else []
        return lines + summary

    def _summary_lines(self) -> List[str]:
        style = self.style
        counts = {"install": 0, "update": 0, "switch": 0, "remove": 0}
        failed = 0
        backups = set()
        touched = set()
        for result in self.results:
            action = result.action
            if not result.ok:
                failed += 1
                continue
            if action.op in counts:
                counts[action.op] += 1
                touched.add(action.harness_id)
            if action.backup:
                backups.add(action.harness_id)
        skipped = sum(1 for a in self.actions if a.op == "skip")
        parts = [f"{counts['install']} installed", f"{counts['update']} updated",
                 f"{counts['switch']} switched", f"{counts['remove']} removed",
                 f"{skipped} skipped"]
        lines = [""]
        if self.install_error:
            lines.append(style.fg(f" {style.glyph('fail')} {self.install_error}", RED))
        head = style.fg(f" {style.glyph('fail')} {failed} failed", RED) if failed else \
            style.fg(f" {style.glyph('ok')} Done", THEME["build"])
        lines.append(head + "  " + ", ".join(parts))
        for harness in self.harnesses:
            if harness.id in backups:
                lines.append(style.fg(f"   Backups in {harness.base / '.pamaga-backups'}", THEME["muted"]))
        for harness in self.harnesses:
            if harness.id in touched:
                lines.append(f"   {harness.restart_hint}")
        return lines

    # overlays

    def _overlay(self, body: List[str], panel: List[str], width: int) -> List[str]:
        if not panel:
            return body
        panel_width = max(display_width(line) for line in panel)
        left = max(0, (width - panel_width) // 2)
        top = max(0, (len(body) - len(panel)) // 2)
        out = list(body)
        for index, line in enumerate(panel):
            if top + index < len(out):
                out[top + index] = " " * left + line
        return out

    def _dialog_box(self, width: int) -> List[str]:
        dialog = self.dialog or {}
        panel_width = min(width - 4, 64)
        lines = [""]
        for text in dialog.get("lines", []):
            lines.extend(wrap(text, panel_width - 4) or [""])
        lines.append("")
        hints = "  ".join(f"{k} {v}" for k, v in dialog.get("hints", ()))
        lines.append(self.style.fg(hints, THEME["muted"]))
        return box(dialog.get("title", ""), lines, panel_width, THEME["think"], self.style)

    def _help_box(self, width: int, height: int) -> List[str]:
        panel_width = min(width - 4, 72)
        lines = []
        for key, text in HELP:
            if key and not text:
                lines.append(self.style.bold(key))
            elif key:
                lines.append(self.style.fg(pad(key, 14), THEME["think"]) + text)
            else:
                lines.append("")
        lines = lines[: max(0, height - 2)]
        return box("Keys (any key closes)", lines, panel_width, THEME["think"], self.style)


def run(ctx, style: Style) -> int:
    """Main loop: read keys, tick, draw, until the app is done."""
    from .terminal import Terminal

    app = App(ctx, style)
    with Terminal() as term:
        while not app.done:
            columns, lines = term.size()
            term.draw(app.render(columns, lines))
            key = term.read_key(0.1)
            if key is not None:
                app.handle(key)
            app.tick()
    return app.exit_code
