"""Tests for scripts/installer/actions.py.

Planning runs against crafted `Installed` records and a stubbed `versions`
callable; applying runs against throwaway directories and a fake HOME, so
the real home is never read or written. There is one test per row of the
planning table in the plan, plus the apply lifecycle, the backup rules, a
simulated copy failure and the force guarantees.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "scripts"))

from installer.actions import (  # noqa: E402
    Action,
    Result,
    Selection,
    apply_actions,
    plan_actions,
)
from installer.catalog import Catalog, Item, content_hash, list_files, load_catalog  # noqa: E402
from installer.harnesses import all_harnesses  # noqa: E402
from installer.state import (  # noqa: E402
    BACKUP_DIR,
    MANIFEST_NAME,
    Installed,
    Manifest,
    Status,
    item_target,
    scan,
)
from installer.versions import ItemVersion  # noqa: E402


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_item(repo: Path, kind: str, name: str, requires=(), user_invocable: bool = True) -> Item:
    source = repo / (kind + "s") / (name + ".md" if kind != "skill" else name)
    return Item(
        kind=kind,
        name=name,
        source=source,
        description=f"{name} does things.",
        user_invocable=user_invocable,
        stage="support",
        tagline="",
        requires=tuple(requires),
        files=tuple(list_files(source)),
        content_hash=content_hash(source),
    )


def stub_versions(label: str = "0.2.0"):
    """A `versions` callable that never touches git."""

    def item_version(item: Item) -> ItemVersion:
        return ItemVersion(
            release=label,
            commit="abc1234",
            date="2026-10-03",
            subject=f"{item.name}: change",
            local_changes=False,
        )

    return item_version


class ToolkitFixture(unittest.TestCase):
    """A fake repository, a fake HOME and helpers to plan against them."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        write(self.repo / "skills" / "alpha" / "SKILL.md", "alpha one\n")
        write(self.repo / "skills" / "alpha" / "references" / "guide.md", "guide\n")
        write(self.repo / "skills" / "beta" / "SKILL.md", "beta one\n")
        write(self.repo / "skills" / "support" / "SKILL.md", "support\n")
        write(self.repo / "agents" / "helper.md", "helper\n")
        write(self.repo / "commands" / "alpha.md", "alpha command\n")
        write(self.repo / "commands" / "beta.md", "beta command\n")
        write(self.repo / "commands" / "support.md", "support command\n")
        self.reload_items()
        self.home = self.root / "home"
        self.harnesses = all_harnesses(scope="user", env={"HOME": str(self.home)})
        self.by_id = {harness.id: harness for harness in self.harnesses}
        self.opencode = self.by_id["opencode"]
        self.claude = self.by_id["claude"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def reload_items(self) -> None:
        """Rebuild the catalog after touching the fake repository."""
        self.alpha = make_item(self.repo, "skill", "alpha")
        self.beta = make_item(self.repo, "skill", "beta", requires=("alpha",))
        self.support = make_item(self.repo, "skill", "support", user_invocable=False)
        self.helper = make_item(self.repo, "agent", "helper")
        self.alpha_command = make_item(self.repo, "command", "alpha")
        self.beta_command = make_item(self.repo, "command", "beta")
        self.support_command = make_item(self.repo, "command", "support")
        self.catalog = Catalog(
            repo=self.repo,
            skills=(self.alpha, self.beta, self.support),
            agents=(self.helper,),
            commands=(self.alpha_command, self.beta_command, self.support_command),
        )

    def select(
        self,
        harnesses=("opencode",),
        skills=(),
        agents=(),
        commands: bool = False,
        mode: str = "link",
        prune: bool = False,
        force=(),
    ) -> Selection:
        return Selection(
            harness_ids=frozenset(harnesses),
            skills=frozenset(skills),
            agents=frozenset(agents),
            commands=commands,
            mode=mode,
            prune=prune,
            force=frozenset(force),
        )

    def plan(self, selection: Selection, scans=None, label: str = "0.2.0"):
        return plan_actions(
            self.catalog, self.harnesses, scans or {}, selection, stub_versions(label)
        )

    def placed(
        self,
        harness,
        item: Item,
        status: Status,
        mode: str | None = None,
        version: str | None = None,
        changed=(),
        managed: bool | None = None,
    ) -> Installed:
        if managed is None:
            managed = status not in (Status.UNMANAGED, Status.FOREIGN_LINK, Status.NOT_INSTALLED)
        if status == Status.FOREIGN_LINK:
            # A live link to somewhere else (a dangling one is replaceable).
            target = item_target(harness, item.kind, item.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not os.path.lexists(target):
                os.symlink(harness.base, target, target_is_directory=True)
        return Installed(
            harness_id=harness.id,
            kind=item.kind,
            name=item.name,
            target=item_target(harness, item.kind, item.name),
            status=status,
            mode=mode,
            installed_version=version,
            link_target=None,
            changed_files=tuple(changed),
            managed=managed,
        )

    def action_for(self, actions, key: str, harness_id: str = "opencode") -> Action:
        kind, _, name = key.partition("/")
        found = [a for a in actions if a.harness_id == harness_id and a.kind == kind and a.name == name]
        self.assertEqual(len(found), 1, f"expected one action for {key}: {found}")
        return found[0]


class PlanningTableTest(ToolkitFixture):
    """One test per row of the planning table in the plan."""

    def test_wanted_and_not_installed_installs(self) -> None:
        actions = self.plan(self.select(skills={"alpha"}))
        self.assertEqual([a.harness_id for a in actions], ["opencode"])
        self.assertEqual(len(actions), 1)
        action = self.action_for(actions, "skill/alpha")
        self.assertEqual(action.op, "install")
        self.assertEqual(action.mode, "link")
        self.assertFalse(action.backup)
        self.assertEqual(action.target, self.opencode.base / "skills" / "alpha")
        self.assertIsNone(action.from_version)
        self.assertEqual(action.to_version, "0.2.0")
        self.assertTrue(action.reason)

    def test_wanted_and_installed_in_the_chosen_mode_keeps(self) -> None:
        cases = (("linked", Status.LINKED, "link"), ("copied", Status.UP_TO_DATE, "copy"))
        for label, status, mode in cases:
            with self.subTest(mode=mode):
                scans = {
                    "opencode": {
                        "skill/alpha": self.placed(
                            self.opencode, self.alpha, status, mode=mode, version="0.1.0"
                        )
                    }
                }
                actions = self.plan(self.select(skills={"alpha"}, mode=mode), scans)
                action = self.action_for(actions, "skill/alpha")
                self.assertEqual(action.op, "keep")
                self.assertEqual(action.mode, mode)
                self.assertFalse(action.backup)

    def test_wanted_in_the_other_mode_switches(self) -> None:
        cases = (
            ("linked to copy", Status.LINKED, "link", "copy"),
            ("copied to link", Status.UP_TO_DATE, "copy", "link"),
            ("outdated to link", Status.OUTDATED, "copy", "link"),
        )
        for label, status, installed_mode, wanted_mode in cases:
            with self.subTest(label):
                scans = {
                    "opencode": {
                        "skill/alpha": self.placed(
                            self.opencode, self.alpha, status, mode=installed_mode
                        )
                    }
                }
                actions = self.plan(self.select(skills={"alpha"}, mode=wanted_mode), scans)
                action = self.action_for(actions, "skill/alpha")
                self.assertEqual(action.op, "switch")
                self.assertEqual(action.mode, wanted_mode)
                self.assertFalse(action.backup)

    def test_keep_modes_leaves_installed_items_in_their_mode(self) -> None:
        cases = (
            ("linked stays linked", Status.LINKED, "link", "copy", "keep"),
            ("copy stays a copy", Status.UP_TO_DATE, "copy", "link", "keep"),
            ("outdated copy is updated as a copy", Status.OUTDATED, "copy", "link", "update"),
        )
        for label, status, installed_mode, default, op in cases:
            with self.subTest(label):
                scans = {
                    "opencode": {
                        "skill/alpha": self.placed(
                            self.opencode, self.alpha, status, mode=installed_mode
                        )
                    }
                }
                selection = replace(self.select(skills={"alpha", "beta"}, mode=default),
                                    keep_modes=True)
                actions = self.plan(selection, scans)
                action = self.action_for(actions, "skill/alpha")
                self.assertEqual(action.op, op)
                self.assertEqual(action.mode, installed_mode)
                # New items still use the selected mode.
                self.assertEqual(self.action_for(actions, "skill/beta").mode, default)

    def test_wanted_outdated_copy_updates(self) -> None:
        scans = {
            "opencode": {
                "skill/alpha": self.placed(
                    self.opencode, self.alpha, Status.OUTDATED, mode="copy", version="0.1.0"
                )
            }
        }
        actions = self.plan(self.select(skills={"alpha"}, mode="copy"), scans)
        action = self.action_for(actions, "skill/alpha")
        self.assertEqual(action.op, "update")
        self.assertEqual(action.mode, "copy")
        self.assertFalse(action.backup)
        self.assertEqual(action.from_version, "0.1.0")
        self.assertEqual(action.to_version, "0.2.0")

    def test_wanted_modified_unmanaged_or_foreign_skips_without_force(self) -> None:
        cases = (
            (Status.MODIFIED, "copy"),
            (Status.UNMANAGED, "copy"),
            (Status.FOREIGN_LINK, "link"),
        )
        for status, installed_mode in cases:
            with self.subTest(status=status):
                scans = {
                    "opencode": {
                        "skill/alpha": self.placed(
                            self.opencode,
                            self.alpha,
                            status,
                            mode=installed_mode,
                            version="0.1.0",
                        )
                    }
                }
                actions = self.plan(self.select(skills={"alpha"}, mode="copy"), scans)
                action = self.action_for(actions, "skill/alpha")
                self.assertEqual(action.op, "skip")
                self.assertFalse(action.backup)
                self.assertIn("overwrite", action.reason)

    def test_wanted_modified_unmanaged_or_foreign_forced_installs_with_backup(self) -> None:
        cases = (
            (Status.MODIFIED, "copy", "copy", "update"),
            (Status.MODIFIED, "copy", "link", "install"),
            (Status.UNMANAGED, "copy", "copy", "install"),
            (Status.FOREIGN_LINK, "link", "link", "install"),
        )
        for status, installed_mode, mode, op in cases:
            with self.subTest(status=status, mode=mode):
                scans = {
                    "opencode": {
                        "skill/alpha": self.placed(
                            self.opencode,
                            self.alpha,
                            status,
                            mode=installed_mode,
                            version="0.1.0",
                        )
                    }
                }
                selection = self.select(
                    skills={"alpha"}, mode=mode, force={"opencode:skill/alpha"}
                )
                action = self.action_for(self.plan(selection, scans), "skill/alpha")
                self.assertEqual(action.op, op)
                self.assertTrue(action.backup)
                self.assertEqual(action.to_version, "0.2.0")

    def test_not_wanted_managed_is_removed_with_prune_and_kept_without_it(self) -> None:
        cases = (
            (Status.LINKED, "link"),
            (Status.UP_TO_DATE, "copy"),
            (Status.OUTDATED, "copy"),
        )
        for status, installed_mode in cases:
            with self.subTest(status=status):
                scans = {
                    "opencode": {
                        "skill/alpha": self.placed(
                            self.opencode,
                            self.alpha,
                            status,
                            mode=installed_mode,
                            version="0.1.0",
                        )
                    }
                }
                kept = self.action_for(self.plan(self.select(skills=set()), scans), "skill/alpha")
                self.assertEqual(kept.op, "keep")
                removed = self.action_for(
                    self.plan(self.select(skills=set(), prune=True), scans), "skill/alpha"
                )
                self.assertEqual(removed.op, "remove")
                self.assertFalse(removed.backup)
                self.assertEqual(removed.from_version, "0.1.0")

    def test_not_wanted_hand_made_identical_copy_is_never_pruned(self) -> None:
        scans = {
            "opencode": {
                "skill/alpha": self.placed(
                    self.opencode, self.alpha, Status.UP_TO_DATE, mode="copy", managed=False
                )
            }
        }
        action = self.action_for(
            self.plan(self.select(skills=set(), prune=True), scans), "skill/alpha"
        )
        self.assertEqual(action.op, "keep")

    def test_wanted_broken_symlink_is_replaced_without_force(self) -> None:
        target = item_target(self.opencode, "skill", "alpha")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(self.opencode.base / "moved-clone" / "alpha", target)
        scans = {
            "opencode": {
                "skill/alpha": self.placed(
                    self.opencode, self.alpha, Status.FOREIGN_LINK, mode="link"
                )
            }
        }
        action = self.action_for(self.plan(self.select(skills={"alpha"}), scans), "skill/alpha")
        self.assertEqual(action.op, "install")
        self.assertTrue(action.backup)

    def test_not_wanted_modified_removed_only_with_prune_and_force(self) -> None:
        scans = {
            "opencode": {
                "skill/alpha": self.placed(
                    self.opencode, self.alpha, Status.MODIFIED, mode="copy", version="0.1.0"
                )
            }
        }
        self.assertEqual(self.action_for(self.plan(self.select(skills=set()), scans), "skill/alpha").op, "keep")
        self.assertEqual(
            self.action_for(self.plan(self.select(skills=set(), prune=True), scans), "skill/alpha").op,
            "keep",
        )
        forced = self.select(skills=set(), prune=True, force={"opencode:skill/alpha"})
        action = self.action_for(self.plan(forced, scans), "skill/alpha")
        self.assertEqual(action.op, "remove")
        self.assertTrue(action.backup)

    def test_orphaned_leftovers(self) -> None:
        # A copy we recorded whose source vanished: removed with prune, backed up.
        gone = Installed(
            harness_id="opencode",
            kind="skill",
            name="gone",
            target=self.opencode.base / "skills" / "gone",
            status=Status.ORPHANED,
            mode="copy",
            installed_version="0.1.0",
            link_target=None,
            changed_files=(),
        )
        scans = {"opencode": {"skill/gone": gone}}
        self.assertEqual(self.plan(self.select(skills=set()), scans), [])
        action = self.action_for(self.plan(self.select(skills=set(), prune=True), scans), "skill/gone")
        self.assertEqual(action.op, "remove")
        self.assertTrue(action.backup)

        # A stray link into the repository: removed without a backup.
        link_gone = Installed(
            harness_id="opencode",
            kind="skill",
            name="retired",
            target=self.opencode.base / "skills" / "retired",
            status=Status.ORPHANED,
            mode="link",
            installed_version=None,
            link_target=str(self.repo / "skills" / "retired"),
            changed_files=(),
        )
        scans = {"opencode": {"skill/retired": link_gone}}
        action = self.action_for(
            self.plan(self.select(skills=set(), prune=True), scans), "skill/retired"
        )
        self.assertEqual(action.op, "remove")
        self.assertFalse(action.backup)

        # A wanted item whose symlink dangles elsewhere is only cleaned by prune.
        alpha = self.placed(self.opencode, self.alpha, Status.ORPHANED, mode="link")
        scans = {"opencode": {"skill/alpha": alpha}}
        self.assertEqual(self.plan(self.select(skills={"alpha"}), scans), [])
        action = self.action_for(
            self.plan(self.select(skills={"alpha"}, prune=True), scans), "skill/alpha"
        )
        self.assertEqual(action.op, "remove")
        self.assertFalse(action.backup)

    def test_commands_in_a_harness_without_support(self) -> None:
        command = self.placed(self.claude, self.alpha_command, Status.LINKED, mode="link")
        scans = {"claude": {"command/alpha": command}}
        kept = self.action_for(
            self.plan(self.select(harnesses=("claude",), skills={"alpha"}, commands=True), scans),
            "command/alpha",
            harness_id="claude",
        )
        self.assertEqual(kept.op, "keep")
        self.assertIn("not supported", kept.reason)
        removed = self.action_for(
            self.plan(
                self.select(harnesses=("claude",), skills={"alpha"}, commands=True, prune=True),
                scans,
            ),
            "command/alpha",
            harness_id="claude",
        )
        self.assertEqual(removed.op, "remove")
        self.assertFalse(removed.backup)

    def test_not_wanted_not_installed_unmanaged_or_foreign_do_nothing(self) -> None:
        cases = (("not installed", Status.NOT_INSTALLED, None), ("unmanaged", Status.UNMANAGED, "copy"), ("foreign", Status.FOREIGN_LINK, "link"))
        for label, status, mode in cases:
            with self.subTest(label):
                scans = {
                    "opencode": {"skill/alpha": self.placed(self.opencode, self.alpha, status, mode=mode)}
                }
                self.assertEqual(self.plan(self.select(skills=set()), scans), [])

    def test_wrappers_follow_wanted_user_invocable_skills_only(self) -> None:
        selection = self.select(
            harnesses=("opencode", "claude"), skills={"alpha"}, commands=True
        )
        actions = self.plan(selection)
        commands = [a for a in actions if a.kind == "command"]
        self.assertEqual(sorted(a.name for a in commands), ["alpha"])
        self.assertEqual({a.harness_id for a in commands}, {"opencode"})
        self.assertTrue(all(a.op == "install" for a in commands))
        skills = {(a.harness_id, a.name) for a in actions if a.kind == "skill"}
        self.assertEqual(skills, {("claude", "alpha")})

    def test_no_wrappers_when_commands_are_off(self) -> None:
        actions = self.plan(self.select(skills={"alpha"}, commands=False))
        self.assertEqual([a.kind for a in actions], ["skill"])

    def test_dependency_closure_pulls_required_skills_in(self) -> None:
        actions = self.plan(self.select(skills={"beta"}))
        self.assertEqual(sorted(a.name for a in actions), ["alpha", "beta"])
        self.assertTrue(all(a.op == "install" for a in actions))

    def test_agents_are_planned_when_selected(self) -> None:
        actions = self.plan(self.select(agents={"helper"}))
        self.assertEqual(
            [(a.kind, a.name, a.op) for a in actions], [("agent", "helper", "install")]
        )

    def test_force_key_is_per_harness(self) -> None:
        scans = {
            "opencode": {
                "agent/helper": self.placed(self.opencode, self.helper, Status.MODIFIED, mode="copy")
            },
            "claude": {
                "agent/helper": self.placed(self.claude, self.helper, Status.MODIFIED, mode="copy")
            },
        }
        selection = self.select(
            harnesses=("opencode", "claude"),
            agents={"helper"},
            mode="copy",
            force={"opencode:agent/helper"},
        )
        actions = self.plan(selection, scans)
        self.assertEqual(self.action_for(actions, "agent/helper", "opencode").op, "update")
        self.assertEqual(self.action_for(actions, "agent/helper", "claude").op, "skip")

    def test_skills_go_only_to_claude_when_both_are_selected(self) -> None:
        # opencode reads ~/.claude/skills, so a second copy would list every skill twice.
        both = self.plan(self.select(harnesses=("opencode", "claude"), skills={"alpha"}))
        self.assertEqual({(a.harness_id, a.op) for a in both if a.kind == "skill"}, {("claude", "install")})
        alone = self.plan(self.select(harnesses=("opencode",), skills={"alpha"}))
        self.assertEqual({(a.harness_id, a.op) for a in alone if a.kind == "skill"}, {("opencode", "install")})

    def test_existing_opencode_skills_are_removed_by_prune_when_both_are_selected(self) -> None:
        scans = {"opencode": {"skill/alpha": self.placed(self.opencode, self.alpha, Status.LINKED)}}
        kept = self.plan(self.select(harnesses=("opencode", "claude"), skills={"alpha"}), scans)
        self.assertEqual(self.action_for(kept, "skill/alpha", "opencode").op, "keep")
        pruned = self.plan(self.select(harnesses=("opencode", "claude"), skills={"alpha"}, prune=True), scans)
        self.assertEqual(self.action_for(pruned, "skill/alpha", "opencode").op, "remove")

    def test_harnesses_outside_the_selection_are_ignored(self) -> None:
        actions = self.plan(self.select(harnesses=("claude",), skills={"alpha"}))
        self.assertEqual({a.harness_id for a in actions}, {"claude"})

    def test_unknown_mode_is_rejected(self) -> None:
        selection = Selection(
            harness_ids=frozenset({"opencode"}),
            skills=frozenset({"alpha"}),
            agents=frozenset(),
            commands=False,
            mode="teleport",
        )
        with self.assertRaises(ValueError):
            self.plan(selection)


class RealCatalogPlanningTest(unittest.TestCase):
    """`make-plan` pulls its dependencies and gets an opencode wrapper only."""

    def test_make_plan_closure_and_wrappers(self) -> None:
        catalog = load_catalog(REPO)
        with tempfile.TemporaryDirectory() as tmp:
            harnesses = all_harnesses(scope="user", env={"HOME": str(Path(tmp) / "home")})
            selection = Selection(
                harness_ids=frozenset({"opencode", "claude"}),
                skills=frozenset({"make-plan"}),
                agents=frozenset(),
                commands=True,
                mode="link",
            )
            actions = plan_actions(catalog, harnesses, {}, selection, stub_versions())
            installs = {(a.harness_id, a.kind, a.name) for a in actions if a.op == "install"}
            for skill in ("make-plan", "plans-convention", "research-topic"):
                self.assertIn(("claude", "skill", skill), installs)
                self.assertNotIn(("opencode", "skill", skill), installs)
            commands = [a for a in actions if a.kind == "command"]
            self.assertEqual(sorted(a.name for a in commands), ["make-plan", "research-topic"])
            self.assertEqual({a.harness_id for a in commands}, {"opencode"})
            # plans-convention is not user-invocable, so it has no wrapper.
            self.assertNotIn("plans-convention", {a.name for a in commands})


class ApplyFixture(ToolkitFixture):
    """`plan_actions` + `apply_actions` against the fake HOME."""

    def setUp(self) -> None:
        super().setUp()
        self.now = datetime(2026, 10, 3, 12, 30, 45)

    def scans(self):
        return {
            harness.id: scan(self.catalog, harness, Manifest.load(harness.base))
            for harness in self.harnesses
        }

    def plan_now(self, selection: Selection, scans=None, label: str = "0.2.0"):
        return plan_actions(
            self.catalog,
            self.harnesses,
            scans if scans is not None else self.scans(),
            selection,
            stub_versions(label),
        )

    def apply(self, actions, on_progress=None):
        return apply_actions(
            actions, self.catalog, self.harnesses, now=self.now, on_progress=on_progress
        )

    def run_plan(self, selection: Selection, scans=None, label: str = "0.2.0"):
        actions = self.plan_now(selection, scans, label)
        return actions, self.apply(actions)

    def assert_only_keeps(self, selection: Selection) -> None:
        actions = self.plan_now(selection)
        self.assertTrue(actions, "expected at least one keep action")
        unexpected = [(a.op, a.kind, a.name) for a in actions if a.op != "keep"]
        self.assertEqual(unexpected, [])


class ApplyLifecycleTest(ApplyFixture):
    """Link, copy, update, switch, remove; the manifest follows each step."""

    def test_link_copy_update_switch_and_remove(self) -> None:
        # 1. install as links; wrappers go to opencode only.
        selection = self.select(skills={"alpha", "beta"}, commands=True, mode="link")
        actions, results = self.run_plan(selection)
        self.assertEqual(sorted(a.op for a in actions), ["install"] * 4)
        self.assertTrue(all(result.ok for result in results))
        alpha = item_target(self.opencode, "skill", "alpha")
        for key in ("skill/alpha", "skill/beta", "command/alpha", "command/beta"):
            target = item_target(self.opencode, *key.split("/"))
            self.assertTrue(target.is_symlink(), target)
        self.assertEqual(os.readlink(alpha), str(self.alpha.source))
        manifest = Manifest.load(self.opencode.base)
        self.assertEqual(manifest.repo, self.repo)
        self.assertEqual(manifest.get("skill/alpha")["mode"], "link")
        self.assertEqual(manifest.get("skill/alpha")["version"], "0.2.0")
        self.assertEqual(sorted(manifest.items), ["command/alpha", "command/beta", "skill/alpha", "skill/beta"])
        self.assert_only_keeps(selection)

        # 2. switch to copies.
        selection = self.select(skills={"alpha", "beta"}, commands=True, mode="copy")
        actions, results = self.run_plan(selection)
        self.assertEqual(sorted(a.op for a in actions), ["switch"] * 4)
        self.assertTrue(all(result.ok for result in results))
        self.assertFalse(alpha.is_symlink())
        self.assertEqual(content_hash(alpha), self.alpha.content_hash)
        self.assertEqual(
            content_hash(item_target(self.opencode, "command", "alpha")),
            self.alpha_command.content_hash,
        )
        manifest = Manifest.load(self.opencode.base)
        self.assertEqual(manifest.get("skill/alpha")["mode"], "copy")
        self.assert_only_keeps(selection)

        # 3. the source moves on: the copy updates.
        write(self.repo / "skills" / "alpha" / "SKILL.md", "alpha two\n")
        self.reload_items()
        selection = self.select(skills={"alpha", "beta"}, commands=True, mode="copy")
        actions, results = self.run_plan(selection, label="0.3.0")
        update = [a for a in actions if a.op != "keep"]
        self.assertEqual(len(update), 1)
        self.assertEqual(update[0].kind, "skill")
        self.assertEqual(update[0].name, "alpha")
        self.assertEqual(update[0].op, "update")
        self.assertEqual(update[0].from_version, "0.2.0")
        self.assertEqual(update[0].to_version, "0.3.0")
        self.assertTrue(all(result.ok for result in results))
        self.assertEqual((alpha / "SKILL.md").read_text(encoding="utf-8"), "alpha two\n")
        self.assertEqual(content_hash(alpha), self.alpha.content_hash)
        manifest = Manifest.load(self.opencode.base)
        self.assertEqual(manifest.get("skill/alpha")["hash"], self.alpha.content_hash)
        self.assertEqual(manifest.get("skill/alpha")["version"], "0.3.0")
        self.assertEqual(scan(self.catalog, self.opencode, manifest)["skill/alpha"].status, Status.UP_TO_DATE)
        self.assert_only_keeps(selection)

        # 4. switch back to links.
        selection = self.select(skills={"alpha", "beta"}, commands=True, mode="link")
        actions, results = self.run_plan(selection)
        self.assertEqual(sorted(a.op for a in actions), ["switch"] * 4)
        self.assertTrue(alpha.is_symlink())
        self.assertEqual(os.readlink(alpha), str(self.alpha.source))
        self.assert_only_keeps(selection)

        # 5. remove the links with prune; the sources stay untouched.
        selection = self.select(skills=set(), commands=False, mode="link", prune=True)
        actions, results = self.run_plan(selection)
        self.assertEqual(sorted(a.op for a in actions), ["remove"] * 4)
        self.assertTrue(all(result.ok for result in results))
        for key in ("skill/alpha", "skill/beta", "command/alpha", "command/beta"):
            target = item_target(self.opencode, *key.split("/"))
            self.assertFalse(os.path.lexists(target), target)
        self.assertTrue((self.repo / "skills" / "alpha").is_dir())
        self.assertEqual(Manifest.load(self.opencode.base).items, {})

        # 6. remove copies in the other harness.
        selection = self.select(harnesses=("claude",), skills={"beta"}, mode="copy")
        actions, results = self.run_plan(selection)
        self.assertEqual(sorted(a.op for a in actions), ["install"] * 2)
        beta = item_target(self.claude, "skill", "beta")
        self.assertEqual(content_hash(beta), self.beta.content_hash)
        selection = self.select(harnesses=("claude",), skills=set(), mode="copy", prune=True)
        actions, results = self.run_plan(selection)
        self.assertEqual(sorted(a.op for a in actions), ["remove"] * 2)
        self.assertFalse(os.path.lexists(beta))
        self.assertEqual(Manifest.load(self.claude.base).items, {})


class ForcedOverwriteTest(ApplyFixture):
    """A MODIFIED copy needs force and moves to the backup dir first."""

    def test_modified_copy_is_skipped_without_force_and_backed_up_with_it(self) -> None:
        selection = self.select(skills={"alpha"}, mode="copy")
        self.run_plan(selection)
        target = item_target(self.opencode, "skill", "alpha")
        write(target / "SKILL.md", "edited by hand\n")

        scanned = self.scans()
        self.assertEqual(scanned["opencode"]["skill/alpha"].status, Status.MODIFIED)
        actions = self.plan_now(selection)
        skip = self.action_for(actions, "skill/alpha")
        self.assertEqual(skip.op, "skip")
        results = self.apply(actions)
        self.assertTrue(all(result.ok for result in results))
        self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "edited by hand\n")
        self.assertFalse((self.opencode.base / BACKUP_DIR).exists())

        forced = self.select(skills={"alpha"}, mode="copy", force={"opencode:skill/alpha"})
        actions, results = self.run_plan(forced)
        update = self.action_for(actions, "skill/alpha")
        self.assertEqual(update.op, "update")
        self.assertTrue(update.backup)
        self.assertTrue(all(result.ok for result in results))
        backup = self.opencode.base / BACKUP_DIR / "20261003-123045" / "skills" / "alpha"
        self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), "edited by hand\n")
        self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "alpha one\n")
        self.assertEqual(sorted(p.name for p in (self.opencode.base / "skills").iterdir()), ["alpha"])
        self.assertEqual(
            sorted(p.name for p in (self.opencode.base / BACKUP_DIR).iterdir()),
            ["20261003-123045"],
        )


class ForceGuaranteeTest(ApplyFixture):
    """Unmanaged dirs and foreign links are never touched without force."""

    def test_unmanaged_directory_survives_without_force(self) -> None:
        target = item_target(self.opencode, "skill", "alpha")
        write(target / "SKILL.md", "mine\n")
        selection = self.select(skills={"alpha"}, mode="copy")
        scanned = self.scans()
        self.assertEqual(scanned["opencode"]["skill/alpha"].status, Status.UNMANAGED)
        actions = self.plan_now(selection)
        self.assertEqual(self.action_for(actions, "skill/alpha").op, "skip")
        results = self.apply(actions)
        self.assertTrue(all(result.ok for result in results))
        self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "mine\n")
        self.assertFalse((self.opencode.base / BACKUP_DIR).exists())
        self.assertFalse((self.opencode.base / MANIFEST_NAME).exists())

        forced = self.select(skills={"alpha"}, mode="copy", force={"opencode:skill/alpha"})
        actions, results = self.run_plan(forced)
        install = self.action_for(actions, "skill/alpha")
        self.assertEqual(install.op, "install")
        self.assertTrue(install.backup)
        self.assertTrue(all(result.ok for result in results))
        self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "alpha one\n")
        backup = self.opencode.base / BACKUP_DIR / "20261003-123045" / "skills" / "alpha"
        self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), "mine\n")

    def test_foreign_symlink_survives_without_force(self) -> None:
        target = item_target(self.opencode, "skill", "alpha")
        target.parent.mkdir(parents=True)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        target.symlink_to(elsewhere, target_is_directory=True)
        selection = self.select(skills={"alpha"}, mode="link")
        scanned = self.scans()
        self.assertEqual(scanned["opencode"]["skill/alpha"].status, Status.FOREIGN_LINK)
        actions = self.plan_now(selection)
        self.assertEqual(self.action_for(actions, "skill/alpha").op, "skip")
        results = self.apply(actions)
        self.assertTrue(all(result.ok for result in results))
        self.assertEqual(os.readlink(target), str(elsewhere))

        forced = self.select(skills={"alpha"}, mode="link", force={"opencode:skill/alpha"})
        actions, results = self.run_plan(forced)
        install = self.action_for(actions, "skill/alpha")
        self.assertEqual(install.op, "install")
        self.assertTrue(install.backup)
        self.assertEqual(os.readlink(target), str(self.alpha.source))
        backup = self.opencode.base / BACKUP_DIR / "20261003-123045" / "skills" / "alpha"
        self.assertTrue(backup.is_symlink())
        self.assertEqual(os.readlink(backup), str(elsewhere))


class CopyFailureTest(ApplyFixture):
    """A copy that dies halfway leaves the previous install intact."""

    def test_failed_copy_keeps_the_previous_install_and_later_actions_run(self) -> None:
        selection = self.select(skills={"alpha", "beta"}, mode="copy")
        self.run_plan(selection)
        alpha = item_target(self.opencode, "skill", "alpha")
        beta = item_target(self.opencode, "skill", "beta")
        before = content_hash(alpha)
        old_manifest = Manifest.load(self.opencode.base).get("skill/alpha")

        write(self.repo / "skills" / "alpha" / "SKILL.md", "alpha two\n")
        self.reload_items()
        shutil.rmtree(beta)

        actions = self.plan_now(selection)
        self.assertEqual(
            [(a.kind, a.name, a.op) for a in actions],
            [("skill", "alpha", "update"), ("skill", "beta", "install")],
        )
        calls = {"count": 0}
        real_copy2 = shutil.copy2

        def flaky_copy2(source, destination, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("no space left on device")
            return real_copy2(source, destination, *args, **kwargs)

        with mock.patch("shutil.copy2", side_effect=flaky_copy2):
            results = self.apply(actions)

        self.assertEqual([result.ok for result in results], [False, True])
        self.assertIn("no space left", results[0].message)
        self.assertEqual(calls["count"], 3)
        # alpha keeps the old copy; the half-written temp is gone.
        self.assertEqual(content_hash(alpha), before)
        self.assertEqual((alpha / "SKILL.md").read_text(encoding="utf-8"), "alpha one\n")
        leftovers = [p.name for p in (self.opencode.base / "skills").iterdir() if "pamaga" in p.name]
        self.assertEqual(leftovers, [])
        # beta was installed after the failure and the manifest was saved.
        self.assertEqual(content_hash(beta), self.beta.content_hash)
        manifest = Manifest.load(self.opencode.base)
        self.assertEqual(manifest.get("skill/alpha"), old_manifest)
        self.assertIn("skill/beta", manifest.items)


class OrphanCleanupTest(ApplyFixture):
    """Stale manifest entries and dangling repo links are cleaned by prune."""

    def test_orphans_are_removed_with_prune(self) -> None:
        manifest = Manifest.load(self.opencode.base)
        manifest.repo = self.repo
        manifest.record(
            "skill/gone",
            mode="copy",
            hash="sha256:whatever",
            version="0.1.0",
            commit=None,
            installed_at="2026-10-01T10:00:00+02:00",
        )
        manifest.save()
        dangling = self.opencode.base / "skills" / "retired"
        dangling.parent.mkdir(parents=True, exist_ok=True)
        dangling.symlink_to(self.repo / "skills" / "retired", target_is_directory=True)

        scanned = self.scans()
        self.assertEqual(scanned["opencode"]["skill/gone"].status, Status.ORPHANED)
        self.assertEqual(scanned["opencode"]["skill/retired"].status, Status.ORPHANED)
        selection = self.select(skills=set(), prune=True)
        actions = self.plan_now(selection)
        gone = self.action_for(actions, "skill/gone")
        self.assertEqual(gone.op, "remove")
        self.assertTrue(gone.backup)
        retired = self.action_for(actions, "skill/retired")
        self.assertEqual(retired.op, "remove")
        self.assertFalse(retired.backup)
        results = self.apply(actions)
        self.assertTrue(all(result.ok for result in results))
        self.assertFalse(os.path.lexists(dangling))
        self.assertEqual(Manifest.load(self.opencode.base).items, {})

    def test_modified_copy_removed_with_prune_and_force_keeps_a_backup(self) -> None:
        selection = self.select(skills={"alpha"}, mode="copy")
        self.run_plan(selection)
        target = item_target(self.opencode, "skill", "alpha")
        write(target / "SKILL.md", "edited\n")
        forced = self.select(
            skills=set(), mode="copy", prune=True, force={"opencode:skill/alpha"}
        )
        actions, results = self.run_plan(forced)
        action = self.action_for(actions, "skill/alpha")
        self.assertEqual(action.op, "remove")
        self.assertTrue(action.backup)
        self.assertTrue(all(result.ok for result in results))
        self.assertFalse(os.path.lexists(target))
        backup = self.opencode.base / BACKUP_DIR / "20261003-123045" / "skills" / "alpha"
        self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), "edited\n")
        self.assertEqual(Manifest.load(self.opencode.base).items, {})


class ProgressTest(ApplyFixture):
    """`on_progress` reports every action, in order."""

    def test_on_progress_covers_every_action(self) -> None:
        selection = self.select(skills={"alpha", "beta"}, mode="link")
        actions = self.plan_now(selection)
        seen = []
        results = self.apply(
            actions, on_progress=lambda done, total, result: seen.append((done, total, result))
        )
        self.assertEqual([done for done, _, _ in seen], [1, 2])
        self.assertEqual({total for _, total, _ in seen}, {2})
        self.assertEqual([item[2].action for item in seen], actions)
        for (_, _, seen_result), result in zip(seen, results):
            self.assertIs(seen_result, result)


class ApplySoftFailureTest(ApplyFixture):
    """A bad action becomes Result(ok=False); nothing else is disturbed."""

    def test_unknown_harness_and_unknown_item_fail_softly(self) -> None:
        unknown_harness = Action(
            "install", "nope", "skill", "alpha", self.root / "elsewhere", "link", False, None,
            "0.2.0", "not installed",
        )
        unknown_item = Action(
            "install", "opencode", "skill", "ghost",
            self.opencode.base / "skills" / "ghost", "copy", False, None, "0.2.0",
            "not installed",
        )
        results = self.apply([unknown_harness, unknown_item])
        self.assertEqual([result.ok for result in results], [False, False])
        self.assertTrue(all(result.message for result in results))
        self.assertIsInstance(results[0], Result)
        self.assertFalse((self.opencode.base / MANIFEST_NAME).exists())

    def test_no_actions_is_fine(self) -> None:
        self.assertEqual(self.apply([]), [])


if __name__ == "__main__":
    unittest.main()
