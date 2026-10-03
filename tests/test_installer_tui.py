"""Tests for the TUI app, driven with a fake context and no terminal involved."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.dont_write_bytecode = True

from installer.actions import Result
from installer.catalog import load_catalog
from installer.harnesses import Harness
from installer.state import Installed, Status
from installer.tui.app import App, AppContext
from installer.tui.style import Style, display_width
from installer.versions import ItemVersion, ToolkitVersion


class World:
    """A fake installer world: two harnesses, injectable scan/apply/pull."""

    def __init__(self, base: Path) -> None:
        self.catalog = load_catalog(REPO)
        self.base = base
        self.project = base / "project"
        self.project.mkdir(parents=True, exist_ok=True)
        self.opencode = Harness(
            id="opencode", label="opencode", base=base / "opencode", binary="opencode",
            supports_commands=True, restart_hint="Restart opencode",
        )
        self.claude = Harness(
            id="claude", label="Claude Code", base=base / "claude", binary="claude",
            supports_commands=False, restart_hint="Restart Claude Code",
        )
        self.opencode.base.mkdir(parents=True, exist_ok=True)
        self.claude.base.mkdir(parents=True, exist_ok=True)
        self.harnesses = [self.opencode, self.claude]
        self.records: dict = {}
        self.remote = "0.9.1"
        self.pull_status_value = (False, "You have uncommitted changes; run git pull yourself.")
        self.pull_calls = 0
        self.applied = []
        self.fail_action_names: set = set()

    def record(self, harness_id, kind, name, status, mode=None, version=None, changed=(),
               managed=False) -> None:
        self.records[(harness_id, f"{kind}/{name}")] = Installed(
            harness_id=harness_id,
            kind=kind,
            name=name,
            target=Path("/nonexistent") / kind / name,
            status=status,
            mode=mode,
            installed_version=version,
            link_target=None,
            changed_files=tuple(changed),
            managed=managed,
        )

    def scan(self, harness: Harness) -> dict:
        return {key: value for (hid, key), value in self.records.items() if hid == harness.id}

    def apply(self, actions, harnesses=None, on_progress=None):
        self.applied.append(list(actions))
        results = []
        for index, action in enumerate(actions):
            ok = action.name not in self.fail_action_names
            result = Result(action=action, ok=ok, message="done" if ok else "simulated failure")
            results.append(result)
            if on_progress is not None:
                on_progress(index + 1, len(actions), result)
        return results

    def context(self) -> AppContext:
        def item_version(item) -> ItemVersion:
            return ItemVersion(
                release="0.2.0", commit="18031b4", date="2026-10-02",
                subject="reviewed plan.md", local_changes=False,
            )

        def pull():
            self.pull_calls += 1
            return True, "Already up to date."

        return AppContext(
            catalog=self.catalog,
            toolkit_version=ToolkitVersion(tag="0.2.0", ahead=0, dirty=False, commit="18031b4"),
            default_mode="link",
            project=self.project,
            harnesses_for=lambda scope: self.harnesses,
            scan=self.scan,
            item_version=item_version,
            apply=self.apply,
            remote_release=lambda: self.remote,
            pull_status=lambda: self.pull_status_value,
            pull=pull,
            reload=self.context,
        )


class TuiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.world = World(Path(self._tmp.name))
        self.style = Style("none", False)
        self.app = App(self.world.context(), self.style)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- helpers -----------------------------------------------------------

    def text(self, width=120, height=30) -> str:
        return "\n".join(self.app.render(width, height))

    def fresh(self, style: Style | None = None) -> App:
        return App(self.world.context(), style or self.style)

    def row_index(self, kind: str, name: str = "") -> int:
        for index, (row_kind, value) in enumerate(self.app._component_rows()):
            if row_kind == kind and (not name or value == name):
                return index
        raise AssertionError(f"row {kind}/{name} not found")

    def at_components(self) -> None:
        self.app.handle("enter")
        self.app.handle("enter")

    def at_review(self) -> None:
        self.at_components()
        self.app.handle("enter")

    def finish_install(self, app: App | None = None) -> App:
        app = app or self.app
        deadline = time.time() + 5
        while app.installing and time.time() < deadline:
            app.tick()
            time.sleep(0.005)
        app.tick()
        return app

    # -- rendering ---------------------------------------------------------

    def test_every_screen_fits_the_terminal(self) -> None:
        for style in (Style("none", False), Style("truecolor", True)):
            for screen in ("splash", "harnesses", "components", "details", "review", "install"):
                app = App(self.world.context(), style)
                if screen != "splash":
                    app.handle("enter")
                if screen in ("components", "details", "review", "install"):
                    app.handle("enter")
                if screen == "details":
                    app.handle("i")
                if screen in ("review", "install"):
                    app.handle("enter")
                if screen == "install":
                    app.handle("enter")
                    self.finish_install(app)
                for width in (60, 80, 109, 110, 160, 220):
                    for height in (18, 24, 50):
                        with self.subTest(style=style.depth, screen=screen, width=width, height=height):
                            lines = app.render(width, height)
                            self.assertEqual(len(lines), height)
                            for line in lines:
                                self.assertLessEqual(display_width(line), width)

    def test_too_small_terminal_message(self) -> None:
        lines = self.app.render(50, 12)
        self.assertEqual(len(lines), 12)
        self.assertIn("Terminal too small", "\n".join(lines))
        for line in lines:
            self.assertLessEqual(display_width(line), 50)

    def test_zero_size_terminal_renders_nothing(self) -> None:
        self.assertEqual(self.app.render(80, 0), [])
        self.assertEqual(self.app.render(0, 24), [])

    def test_splash_shows_version_wordmark_and_harness_summary(self) -> None:
        body = self.text()
        self.assertIn("0.2.0", body)
        self.assertIn("Macaco giving macacos instructions", body)
        self.assertIn("opencode", body)
        self.assertIn("detected", body)

    def test_help_overlay_opens_and_closes(self) -> None:
        self.app.handle("?")
        self.assertTrue(self.app.show_help)
        self.assertIn("this help", self.text())
        self.app.handle("x")
        self.assertFalse(self.app.show_help)
        self.assertNotIn("this help", self.text())

    # -- flow --------------------------------------------------------------

    def test_flow_forward_and_back(self) -> None:
        self.assertEqual(self.app.screen, "splash")
        self.app.handle("enter")
        self.assertEqual(self.app.screen, "harnesses")
        self.app.handle("esc")
        self.assertEqual(self.app.screen, "splash")
        self.app.handle("enter")
        self.app.handle("enter")
        self.assertEqual(self.app.screen, "components")
        self.app.handle("i")
        self.assertEqual(self.app.screen, "details")
        self.app.handle("esc")
        self.assertEqual(self.app.screen, "components")
        self.app.handle("enter")
        self.assertEqual(self.app.screen, "review")
        self.app.handle("esc")
        self.assertEqual(self.app.screen, "components")

    def test_arrows_move_between_steps_but_never_apply(self) -> None:
        self.app.handle("right")
        self.assertEqual(self.app.screen, "harnesses")
        self.app.handle("right")
        self.assertEqual(self.app.screen, "components")
        self.app.handle("right")
        self.assertEqual(self.app.screen, "review")
        self.app.handle("right")
        self.assertEqual(self.app.screen, "review")
        self.assertEqual(self.world.applied, [])
        for screen in ("components", "harnesses", "splash"):
            self.app.handle("left")
            self.assertEqual(self.app.screen, screen)

    def test_footer_says_what_to_do_and_which_keys(self) -> None:
        self.at_components()
        body = self.text(120, 30)
        self.assertIn("Space marks", body)
        self.assertIn("space mark", body)
        self.assertIn("right review", body)
        self.assertNotIn("u mark updates", body)

    def test_a_toggles_all_and_none(self) -> None:
        self.at_components()
        self.app.handle("n")
        self.app.handle("a")
        self.assertEqual(self.app.chosen, {s.name for s in self.world.catalog.skills})
        self.app.handle("a")
        self.assertEqual(self.app.chosen, set())

    def test_skill_rows_say_what_apply_will_do(self) -> None:
        self.world.record("opencode", "skill", "make-plan", Status.OUTDATED, mode="copy", version="0.1.0")
        self.world.record("opencode", "skill", "find-bug", Status.LINKED, mode="link")
        self.world.record("claude", "skill", "find-bug", Status.LINKED, mode="link")
        self.app = self.fresh()
        self.at_components()
        self.app.chosen.discard("find-bug")
        self.app.chosen.add("deep-review")
        lines = self.app.render(120, 40)
        line = lambda name: next(l for l in lines if f" {name} " in l)
        self.assertIn("update", line("make-plan"))
        self.assertIn("remove", line("find-bug"))
        self.assertIn("install", line("deep-review"))

    def test_skills_read_from_claude_show_as_installed_in_opencode(self) -> None:
        # opencode reads ~/.claude/skills: a skill there is installed for it too.
        self.world.opencode = replace(self.world.opencode, skills_from=("claude",))
        self.world.harnesses = [self.world.opencode, self.world.claude]
        target = self.world.claude.base / "skills" / "find-bug"
        target.mkdir(parents=True)
        self.world.record("claude", "skill", "find-bug", Status.LINKED, mode="link", version="0.2.0",
                          managed=True)
        self.world.records[("claude", "skill/find-bug")] = replace(
            self.world.records[("claude", "skill/find-bug")], target=target)
        self.app = self.fresh()
        self.assertIn("1 via Claude Code", self.app._counts("opencode"))
        self.app.checked = {"opencode"}
        self.at_components()
        lines = self.app.render(120, 40)
        line = lambda name: next(l for l in lines if f" {name} " in l)
        self.assertNotIn("install in", line("find-bug"))
        self.assertIn("installed", line("find-bug"))
        self.assertIn("via Claude Code (0.2.0)", "\n".join(self.app._details_lines(
            self.world.catalog.get("skill", "find-bug"), 80)))
        self.app.handle("enter")
        review = self.text(160, 40)
        self.assertIn("opencode reads", review)
        self.assertFalse(any(a.kind == "skill" and a.name == "find-bug" for a in self.app.actions))

    def test_unmarked_hand_made_copy_is_not_shown_as_removed(self) -> None:
        # The plan keeps an identical copy the installer did not make.
        self.world.record("opencode", "skill", "find-bug", Status.UP_TO_DATE, mode="copy")
        self.world.record("opencode", "skill", "make-plan", Status.UP_TO_DATE, mode="copy", managed=True)
        self.app = self.fresh()
        self.at_components()
        self.app.chosen.discard("find-bug")
        self.app.chosen.discard("make-plan")
        lines = self.app.render(120, 40)
        line = lambda name: next(l for l in lines if f" {name} " in l)
        self.assertNotIn("remove", line("find-bug"))
        self.assertIn("remove", line("make-plan"))

    def test_cursor_stays_visible_below_the_settings_header(self) -> None:
        self.at_components()
        self.app.handle("end")
        self.assertEqual(self.app.cursor, len(self.app._component_rows()) - 1)
        for height in (8, 12, 18):
            with self.subTest(height=height):
                lines = self.app._component_lines(100, height)
                self.assertTrue(any(line.startswith(self.style.glyph("arrow")) for line in lines))

    def test_quit_asks_when_selection_changed(self) -> None:
        self.at_components()
        self.app.handle("n")
        self.app.handle("q")
        self.assertIsNotNone(self.app.dialog)
        self.assertEqual(self.app.dialog["kind"], "quit")
        self.assertIn("Quit anyway?", self.text())
        self.app.handle("esc")
        self.assertIsNone(self.app.dialog)
        self.assertFalse(self.app.done)
        self.app.handle("q")
        self.app.handle("enter")
        self.assertTrue(self.app.done)

    def test_scope_toggle(self) -> None:
        self.app.handle("enter")
        self.app.handle("s")
        self.assertEqual(self.app.scope, "project")
        self.app.handle("s")
        self.assertEqual(self.app.scope, "user")

    # -- components --------------------------------------------------------

    def test_selecting_make_plan_selects_its_closure(self) -> None:
        self.at_components()
        self.app.handle("n")
        self.app.cursor = self.row_index("skill", "make-plan")
        self.app.handle("space")
        self.assertIn("make-plan", self.app.chosen)
        self.assertLessEqual(
            {"plans-convention", "research-topic"}, self.app._wanted()
        )

    def test_required_skill_cannot_be_unselected(self) -> None:
        self.at_components()
        self.app.handle("n")
        self.app.cursor = self.row_index("skill", "make-plan")
        self.app.handle("space")
        self.app.cursor = self.row_index("skill", "plans-convention")
        self.app.handle("space")
        self.assertIn("required by", self.app.notice)
        self.assertIn("plans-convention", self.app._wanted())

    def test_u_selects_exactly_the_outdated_skills(self) -> None:
        self.world.record("opencode", "skill", "make-plan", Status.OUTDATED, mode="copy", version="0.1.0")
        self.app = self.fresh()
        self.at_components()
        self.app.handle("n")
        self.app.handle("u")
        self.assertEqual(self.app.chosen, {"make-plan"})
        self.assertIn("Selected 1", self.app.notice)

    def test_filter_by_name_and_clear(self) -> None:
        self.at_components()
        self.app.handle("/")
        for char in "make":
            self.app.handle(char)
        names = [value for kind, value in self.app._component_rows() if kind == "skill"]
        self.assertIn("make-plan", names)
        self.assertNotIn("find-bug", names)
        self.app.handle("esc")
        self.assertFalse(self.app.filtering)
        self.assertEqual(self.app.filter, "")

    def test_mode_and_wrappers_toggle(self) -> None:
        self.at_components()
        self.app.cursor = self.row_index("option", "mode")
        self.app.handle("space")
        self.assertEqual(self.app.mode, "copy")
        self.app.cursor = self.row_index("option", "commands")
        self.app.handle("space")
        self.assertFalse(self.app.commands)

    def test_installed_items_keep_their_mode_until_the_mode_is_changed(self) -> None:
        self.world.record("opencode", "skill", "make-plan", Status.LINKED, mode="link")
        self.world.record("claude", "skill", "make-plan", Status.UP_TO_DATE, mode="copy")
        self.app = self.fresh()
        self.app.checked = {"opencode", "claude"}
        self.assertFalse([a for a in self.app._plan() if a.op == "switch"])
        self.at_components()
        self.app.cursor = self.row_index("option", "mode")
        self.app.handle("space")
        self.assertTrue([a for a in self.app._plan() if a.op == "switch"])

    def test_details_pane_at_110_shows_changed_files(self) -> None:
        self.world.record(
            "opencode", "skill", "make-plan", Status.OUTDATED, mode="copy",
            version="0.1.0", changed=("~ SKILL.md",),
        )
        self.app = self.fresh()
        self.at_components()
        self.app.cursor = self.row_index("skill", "make-plan")
        body = self.text(120, 50)
        self.assertIn("update 0.1.0", body)
        self.assertIn("/make-plan", body)

    def test_details_show_what_it_does_not_when_to_load_it(self) -> None:
        self.at_components()
        self.app.cursor = self.row_index("skill", "make-plan")
        body = self.text(120, 50)
        self.assertIn("Turn a feature", body)
        self.assertNotIn("Use when", body)

    def test_what_it_does_cuts_the_trigger_sentences(self) -> None:
        from installer.tui.app import what_it_does
        self.assertEqual(what_it_does("Do X. Use when the user asks."), "Do X.")
        self.assertEqual(what_it_does("Where plans live. Load it before x."), "Where plans live.")
        self.assertEqual(what_it_does("No trigger here."), "No trigger here.")

    def test_details_full_screen_below_110(self) -> None:
        self.world.record(
            "opencode", "skill", "make-plan", Status.OUTDATED, mode="copy",
            version="0.1.0", changed=("~ SKILL.md",),
        )
        self.app = self.fresh()
        self.at_components()
        self.app.cursor = self.row_index("skill", "make-plan")
        self.assertNotIn("/make-plan", self.text(100, 30))
        self.app.handle("i")
        self.assertEqual(self.app.screen, "details")
        body = self.text(100, 50)
        self.assertIn("Command", body)
        self.assertIn("/make-plan", body)
        self.assertIn("~ SKILL.md", body)
        self.app.handle("esc")
        self.assertEqual(self.app.screen, "components")

    # -- review and install ------------------------------------------------

    def test_review_lists_actions_and_force_toggles(self) -> None:
        self.world.record("opencode", "skill", "make-plan", Status.UNMANAGED)
        self.app = self.fresh()
        self.at_review()
        body = self.text(120, 40)
        self.assertIn("skip", body)
        self.assertIn("not installed by the toolkit", body)
        self.assertIn("opencode:skill/make-plan", self.app.candidates)
        for index, (kind, value) in enumerate(self.app._review_rows()):
            if kind == "action" and self.app._candidate_key(value) == "opencode:skill/make-plan":
                self.app.review_cursor = index
                break
        self.app.handle("space")
        self.assertIn("opencode:skill/make-plan", self.app.force)
        self.assertTrue(any(a.op == "install" and a.backup for a in self.app.actions))

    def test_review_says_up_to_date_and_exits(self) -> None:
        self.at_components()
        self.app.handle("n")
        self.app.handle("enter")
        self.assertIn("Everything is up to date", self.text())
        self.app.handle("enter")
        self.assertTrue(self.app.done)
        self.assertEqual(self.app.exit_code, 0)

    def test_install_progress_reaches_total(self) -> None:
        self.at_review()
        self.assertGreater(len(self.app.actions), 0)
        self.app.handle("enter")
        self.assertEqual(self.app.screen, "install")
        self.finish_install()
        self.assertFalse(self.app.installing)
        done, total = self.app.progress
        self.assertEqual((done, total), (total, total))
        self.assertGreater(total, 0)
        self.assertIn("Done", self.text())
        self.app.handle("enter")
        self.assertTrue(self.app.done)
        self.assertEqual(self.app.exit_code, 0)

    def test_ctrl_c_waits_while_installing(self) -> None:
        # Quitting mid-install would kill the worker before the manifests are saved.
        self.app.installing = True
        self.app.handle("ctrl-c")
        self.assertFalse(self.app.done)
        self.assertIn("Wait for the installation", self.app.notice)
        self.app.installing = False
        self.app.handle("ctrl-c")
        self.assertTrue(self.app.done)
        self.assertEqual(self.app.exit_code, 130)

    def test_install_failure_sets_exit_code_one(self) -> None:
        self.world.fail_action_names = {"make-plan"}
        self.app = self.fresh()
        self.at_review()
        self.app.handle("enter")
        self.finish_install()
        self.assertEqual(self.app.exit_code, 1)
        self.assertIn("failed", self.text())

    # -- updates -----------------------------------------------------------

    def test_remote_notice_appears_after_tick(self) -> None:
        self.assertNotIn("0.9.1", self.text())
        deadline = time.time() + 5
        while self.app.remote is None and time.time() < deadline:
            self.app.tick()
            time.sleep(0.005)
        self.assertEqual(self.app.remote, "0.9.1")
        self.assertIn("0.9.1", self.text())

    def test_dev_channel_shows_badge_and_notice(self) -> None:
        self.assertNotIn("[dev]", self.app._header(120))
        context = self.world.context()
        context.toolkit_version = ToolkitVersion(
            tag="0.2.0", ahead=0, dirty=False, commit="18031b4", dev=True)
        context.remote_dev_commit = lambda: "deadbeef" * 5
        app = App(context, self.style)
        deadline = time.time() + 5
        while app.remote is None and time.time() < deadline:
            app.tick()
            time.sleep(0.005)
        self.assertIn("[dev]", app._header(120))
        self.assertIn("Development build", "\n".join(app.render(120, 30)))
        app.handle("U")
        dialog = "\n".join(app.dialog["lines"])
        self.assertIn("newer stable release exists: 0.9.1", dialog)
        self.assertIn("origin/dev has newer commits (deadbee)", dialog)

    def test_pull_refused_shows_reason_and_does_not_pull(self) -> None:
        self.app.handle("U")
        self.assertIsNotNone(self.app.dialog)
        self.assertFalse(self.app.dialog["can"])
        self.assertIn("uncommitted", self.text())
        self.assertEqual(self.world.pull_calls, 0)


if __name__ == "__main__":
    unittest.main()
