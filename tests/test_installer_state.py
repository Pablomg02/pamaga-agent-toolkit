"""Tests for scripts/installer/harnesses.py and scripts/installer/state.py.

Everything runs against throwaway directories and a fake HOME: the real
home is never read or written. `Item` and `Catalog` come from
`installer.catalog` (T1) and are only constructed here, never redefined.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "scripts"))

from installer.catalog import Catalog, Item, content_hash, list_files  # noqa: E402
from installer.harnesses import Harness, all_harnesses  # noqa: E402
from installer.state import (  # noqa: E402
    BACKUP_DIR,
    MANIFEST_NAME,
    Installed,
    Manifest,
    Status,
    item_target,
    scan,
)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_item(repo: Path, kind: str, name: str) -> Item:
    source = repo / (kind + "s") / (name + ".md" if kind != "skill" else name)
    return Item(
        kind=kind,
        name=name,
        source=source,
        description=f"{name} does things.",
        user_invocable=True,
        stage="support",
        tagline="",
        requires=(),
        files=tuple(list_files(source)),
        content_hash=content_hash(source),
    )


def make_harness(base: Path, harness_id: str = "opencode") -> Harness:
    if harness_id == "claude":
        return Harness(
            id="claude",
            label="Claude Code",
            base=base,
            binary="claude",
            supports_commands=False,
            restart_hint="Restart Claude Code to pick up the changes.",
        )
    return Harness(
        id="opencode",
        label="opencode",
        base=base,
        binary="opencode",
        supports_commands=True,
        restart_hint="Restart opencode to pick up the changes.",
    )


def copy_item(item: Item, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if item.source.is_dir():
        shutil.copytree(item.source, target)
    else:
        shutil.copy2(item.source, target)


class HarnessTest(unittest.TestCase):
    """`all_harnesses` resolves bases from a fake env, never the real home."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_user_scope_defaults_under_home(self) -> None:
        home = self.root / "home"
        harnesses = all_harnesses(env={"HOME": str(home)})
        self.assertEqual([h.id for h in harnesses], ["opencode", "claude"])
        self.assertEqual(harnesses[0].base, home / ".config" / "opencode")
        self.assertEqual(harnesses[1].base, home / ".claude")

    def test_xdg_config_home_wins_for_opencode(self) -> None:
        home = self.root / "home"
        xdg = self.root / "xdg"
        harnesses = all_harnesses(env={"HOME": str(home), "XDG_CONFIG_HOME": str(xdg)})
        self.assertEqual(harnesses[0].base, xdg / "opencode")
        self.assertEqual(harnesses[1].base, home / ".claude")

    def test_userprofile_fallback_on_windows(self) -> None:
        profile = self.root / "profile"
        harnesses = all_harnesses(env={"USERPROFILE": str(profile)})
        self.assertEqual(harnesses[0].base, profile / ".config" / "opencode")
        self.assertEqual(harnesses[1].base, profile / ".claude")

    def test_project_scope(self) -> None:
        project = self.root / "project"
        harnesses = all_harnesses(scope="project", project=project, env={})
        self.assertEqual(harnesses[0].base, project / ".opencode")
        self.assertEqual(harnesses[1].base, project / ".claude")

    def test_project_scope_defaults_to_cwd(self) -> None:
        with mock.patch("installer.harnesses.Path.cwd", return_value=self.root):
            harnesses = all_harnesses(scope="project", env={})
        self.assertEqual(harnesses[0].base, self.root / ".opencode")
        self.assertEqual(harnesses[1].base, self.root / ".claude")

    def test_unknown_scope_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            all_harnesses(scope="galaxy", env={})

    def test_labels_capabilities_and_restart_hints(self) -> None:
        opencode, claude = all_harnesses(env={"HOME": str(self.root / "home")})
        self.assertEqual((opencode.label, opencode.binary), ("opencode", "opencode"))
        self.assertTrue(opencode.supports_commands)
        self.assertEqual((claude.label, claude.binary), ("Claude Code", "claude"))
        self.assertFalse(claude.supports_commands)
        self.assertTrue(opencode.restart_hint)
        self.assertTrue(claude.restart_hint)

    def test_dir_for(self) -> None:
        harness = all_harnesses(env={"HOME": str(self.root / "home")})[0]
        self.assertEqual(harness.dir_for("skill"), harness.base / "skills")
        self.assertEqual(harness.dir_for("agent"), harness.base / "agents")
        self.assertEqual(harness.dir_for("command"), harness.base / "commands")
        with self.assertRaises(ValueError):
            harness.dir_for("widget")

    def test_detected_checks_the_base_and_the_binary(self) -> None:
        harness = all_harnesses(env={"HOME": str(self.root / "home")})[0]
        with mock.patch("installer.harnesses.shutil.which", return_value=None):
            self.assertFalse(harness.detected())
        with mock.patch("installer.harnesses.shutil.which", return_value="/usr/bin/opencode"):
            self.assertTrue(harness.detected())
        harness.base.mkdir(parents=True)
        with mock.patch("installer.harnesses.shutil.which", return_value=None):
            self.assertTrue(harness.detected())


class StateFixture(unittest.TestCase):
    """A fake repository with two skills, one agent and one command."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        write(self.repo / "skills" / "alpha" / "SKILL.md", "alpha one\n")
        write(self.repo / "skills" / "alpha" / "references" / "guide.md", "guide\n")
        write(self.repo / "skills" / "beta" / "SKILL.md", "beta\n")
        write(self.repo / "agents" / "helper.md", "helper agent\n")
        write(self.repo / "commands" / "alpha.md", "command alpha\n")
        self.alpha = make_item(self.repo, "skill", "alpha")
        self.beta = make_item(self.repo, "skill", "beta")
        self.helper = make_item(self.repo, "agent", "helper")
        self.alpha_command = make_item(self.repo, "command", "alpha")
        self.catalog = self.build_catalog()
        self.base = self.root / "base"
        self.harness = make_harness(self.base)
        self.manifest = Manifest.load(self.base)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def build_catalog(self) -> Catalog:
        return Catalog(
            repo=self.repo,
            skills=(self.alpha, self.beta),
            agents=(self.helper,),
            commands=(self.alpha_command,),
        )

    def reload_catalog(self) -> None:
        """Rebuild the catalog after touching the fake repository."""
        self.alpha = make_item(self.repo, "skill", "alpha")
        self.catalog = self.build_catalog()

    def record(self, key: str, **overrides: object) -> None:
        entry = {
            "mode": "copy",
            "hash": "sha256:old",
            "version": "0.1.0",
            "commit": "abc1234",
            "installed_at": "2026-10-01T10:00:00+02:00",
        }
        entry.update(overrides)
        self.manifest.record(key, **entry)


class ScanStatusTableTest(StateFixture):
    """One test per row of the status table in the plan."""

    def test_not_installed(self) -> None:
        result = scan(self.catalog, self.harness, self.manifest)
        self.assertEqual(
            sorted(result), ["agent/helper", "command/alpha", "skill/alpha", "skill/beta"]
        )
        alpha = result["skill/alpha"]
        self.assertEqual(alpha.status, Status.NOT_INSTALLED)
        self.assertEqual(alpha.harness_id, "opencode")
        self.assertEqual(alpha.target, self.base / "skills" / "alpha")
        self.assertIsNone(alpha.mode)
        self.assertIsNone(alpha.installed_version)
        self.assertIsNone(alpha.link_target)
        self.assertEqual(alpha.changed_files, ())

    def test_linked(self) -> None:
        target = self.base / "skills" / "alpha"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.repo / "skills" / "alpha", target_is_directory=True)
        self.record("skill/alpha", mode="copy", hash="sha256:whatever")
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.LINKED)
        self.assertEqual(alpha.mode, "link")
        self.assertEqual(alpha.link_target, str(self.repo / "skills" / "alpha"))
        self.assertEqual(alpha.installed_version, "0.1.0")
        self.assertEqual(alpha.changed_files, ())

    def test_linked_file_item(self) -> None:
        target = self.base / "agents" / "helper.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.repo / "agents" / "helper.md")
        helper = scan(self.catalog, self.harness, self.manifest)["agent/helper"]
        self.assertEqual(helper.status, Status.LINKED)
        self.assertEqual(helper.mode, "link")

    def test_foreign_link(self) -> None:
        target = self.base / "skills" / "alpha"
        target.parent.mkdir(parents=True)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        cases = {
            "outside the repo": elsewhere,
            "another item of the repo": self.repo / "skills" / "beta",
            "dangling outside the repo": self.root / "missing",
        }
        for label, destination in cases.items():
            with self.subTest(label):
                if target.is_symlink():
                    target.unlink()
                elif target.exists():
                    shutil.rmtree(target)
                target.symlink_to(destination, target_is_directory=True)
                alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
                self.assertEqual(alpha.status, Status.FOREIGN_LINK)
                self.assertEqual(alpha.mode, "link")
                self.assertEqual(alpha.link_target, str(destination))

    def test_up_to_date(self) -> None:
        copy_item(self.alpha, self.base / "skills" / "alpha")
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.UP_TO_DATE)
        self.assertEqual(alpha.mode, "copy")
        self.assertIsNone(alpha.installed_version)
        self.assertEqual(alpha.changed_files, ())
        # The hash matches the source, so the row holds with an entry too.
        self.record("skill/alpha", hash="sha256:old")
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.UP_TO_DATE)
        self.assertEqual(alpha.installed_version, "0.1.0")

    def test_up_to_date_file_item(self) -> None:
        copy_item(self.alpha_command, self.base / "commands" / "alpha.md")
        result = scan(self.catalog, self.harness, self.manifest)
        self.assertEqual(result["command/alpha"].status, Status.UP_TO_DATE)
        self.assertEqual(result["command/alpha"].mode, "copy")

    def test_outdated(self) -> None:
        target = self.base / "skills" / "alpha"
        copy_item(self.alpha, target)
        self.record("skill/alpha", hash=content_hash(target))
        write(self.repo / "skills" / "alpha" / "SKILL.md", "alpha two\n")
        self.reload_catalog()
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.OUTDATED)
        self.assertEqual(alpha.mode, "copy")
        self.assertEqual(alpha.installed_version, "0.1.0")
        self.assertEqual(alpha.changed_files, ("~ SKILL.md",))

    def test_modified(self) -> None:
        target = self.base / "skills" / "alpha"
        copy_item(self.alpha, target)
        self.record("skill/alpha", hash=content_hash(target))
        write(target / "SKILL.md", "edited by hand\n")
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.MODIFIED)
        self.assertEqual(alpha.mode, "copy")
        self.assertEqual(alpha.changed_files, ("~ SKILL.md",))

    def test_unmanaged(self) -> None:
        target = self.base / "skills" / "alpha"
        copy_item(self.alpha, target)
        write(target / "SKILL.md", "hand made\n")
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.UNMANAGED)
        self.assertEqual(alpha.mode, "copy")
        self.assertIsNone(alpha.installed_version)
        self.assertEqual(alpha.changed_files, ("~ SKILL.md",))

    def test_orphaned_from_stale_manifest_entry(self) -> None:
        self.record("skill/concurrent-work", mode="link")
        self.record("skill/gone-copy", mode="copy")
        shutil.copytree(self.repo / "skills" / "beta", self.base / "skills" / "gone-copy")
        result = scan(self.catalog, self.harness, self.manifest)
        missing = result["skill/concurrent-work"]
        self.assertEqual(missing.status, Status.ORPHANED)
        self.assertEqual(missing.mode, "link")
        self.assertEqual(missing.installed_version, "0.1.0")
        self.assertEqual(missing.target, self.base / "skills" / "concurrent-work")
        self.assertIsNone(missing.link_target)
        self.assertEqual(missing.changed_files, ())
        gone = result["skill/gone-copy"]
        self.assertEqual(gone.status, Status.ORPHANED)
        self.assertEqual(gone.mode, "copy")

    def test_orphaned_from_dangling_symlink_into_the_repo(self) -> None:
        target = self.base / "skills" / "concurrent-work"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.repo / "skills" / "concurrent-work", target_is_directory=True)
        orphan = scan(self.catalog, self.harness, self.manifest)["skill/concurrent-work"]
        self.assertEqual(orphan.status, Status.ORPHANED)
        self.assertEqual(orphan.mode, "link")
        self.assertEqual(orphan.target, target)
        self.assertEqual(orphan.link_target, str(self.repo / "skills" / "concurrent-work"))
        self.assertEqual(orphan.changed_files, ())

    def test_orphaned_dangling_command_symlink(self) -> None:
        target = self.base / "commands" / "retired.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.repo / "commands" / "retired.md")
        orphan = scan(self.catalog, self.harness, self.manifest)["command/retired"]
        self.assertEqual(orphan.status, Status.ORPHANED)
        self.assertEqual(orphan.mode, "link")
        self.assertEqual(orphan.target, target)

    def test_command_symlink_in_a_claude_base_is_reported(self) -> None:
        claude = make_harness(self.base, "claude")
        self.assertFalse(claude.supports_commands)
        target = self.base / "commands" / "alpha.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.repo / "commands" / "alpha.md")
        result = scan(self.catalog, claude, self.manifest)
        alpha = result["command/alpha"]
        self.assertEqual(alpha.status, Status.LINKED)
        self.assertEqual(alpha.mode, "link")
        self.assertEqual(alpha.harness_id, "claude")
        # Commands of a harness that does not support them are still listed.
        self.assertEqual(result["skill/beta"].status, Status.NOT_INSTALLED)

    def test_changed_files_lists_added_removed_and_changed(self) -> None:
        target = self.base / "skills" / "alpha"
        copy_item(self.alpha, target)
        (target / "references" / "guide.md").unlink()
        write(target / "extra.md", "extra\n")
        write(target / "SKILL.md", "edited\n")
        alpha = scan(self.catalog, self.harness, self.manifest)["skill/alpha"]
        self.assertEqual(alpha.status, Status.UNMANAGED)
        self.assertEqual(
            alpha.changed_files, ("+ extra.md", "- references/guide.md", "~ SKILL.md")
        )

    def test_changed_files_for_a_file_item(self) -> None:
        target = self.base / "commands" / "alpha.md"
        copy_item(self.alpha_command, target)
        write(target, "edited command\n")
        result = scan(self.catalog, self.harness, self.manifest)
        self.assertEqual(result["command/alpha"].changed_files, ("~ alpha.md",))


class ManifestTest(unittest.TestCase):
    """The manifest round-trips, survives corruption and saves atomically."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.base = self.root / "base"
        self.repo = self.root / "repo"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def record(self, manifest: Manifest, **overrides: object) -> None:
        entry = {
            "mode": "copy",
            "hash": "sha256:abc",
            "version": "0.2.0",
            "commit": "18031b4",
            "installed_at": "2026-10-03T12:00:00+02:00",
        }
        entry.update(overrides)
        manifest.record("skill/alpha", **entry)

    def test_names(self) -> None:
        self.assertEqual(MANIFEST_NAME, ".pamaga-toolkit.json")
        self.assertEqual(BACKUP_DIR, ".pamaga-backups")

    def test_missing_file_is_empty(self) -> None:
        manifest = Manifest.load(self.base)
        self.assertEqual(manifest.items, {})
        self.assertIsNone(manifest.get("skill/alpha"))
        self.assertIsNone(manifest.repo)

    def test_round_trip(self) -> None:
        manifest = Manifest.load(self.base)
        manifest.repo = self.repo
        self.record(manifest)
        manifest.record(
            "agent/helper",
            mode="link",
            hash="sha256:def",
            version=None,
            commit=None,
            installed_at="2026-10-03T12:01:00+02:00",
        )
        manifest.save()

        loaded = Manifest.load(self.base)
        self.assertEqual(loaded.repo, self.repo)
        self.assertEqual(
            loaded.get("skill/alpha"),
            {
                "mode": "copy",
                "hash": "sha256:abc",
                "version": "0.2.0",
                "commit": "18031b4",
                "installed_at": "2026-10-03T12:00:00+02:00",
            },
        )
        self.assertEqual(
            loaded.get("agent/helper"),
            {
                "mode": "link",
                "hash": "sha256:def",
                "version": None,
                "commit": None,
                "installed_at": "2026-10-03T12:01:00+02:00",
            },
        )
        data = json.loads((self.base / MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["repo"], str(self.repo))
        self.assertEqual(sorted(data["items"]), ["agent/helper", "skill/alpha"])

    def test_record_overwrites_and_forget_removes(self) -> None:
        manifest = Manifest.load(self.base)
        self.record(manifest, hash="sha256:one")
        self.record(manifest, hash="sha256:two")
        self.assertEqual(list(manifest.items), ["skill/alpha"])
        self.assertEqual(manifest.get("skill/alpha")["hash"], "sha256:two")
        manifest.forget("skill/alpha")
        self.assertIsNone(manifest.get("skill/alpha"))
        manifest.forget("skill/alpha")

    def test_valid_empty_manifest_is_kept(self) -> None:
        self.base.mkdir()
        path = self.base / MANIFEST_NAME
        path.write_text('{"schema": 1, "items": {}}', encoding="utf-8")
        manifest = Manifest.load(self.base)
        self.assertEqual(manifest.items, {})
        self.assertTrue(path.exists())
        self.assertFalse((self.base / (MANIFEST_NAME + ".bak")).exists())

    def test_corrupt_file_is_moved_to_bak_and_treated_as_empty(self) -> None:
        cases = ("{not json", "[]", '{"items": "nope"}', "", b"\xff\xfe\x00not text")
        for index, text in enumerate(cases):
            with self.subTest(text=text):
                base = self.root / f"corrupt{index}"
                base.mkdir()
                path = base / MANIFEST_NAME
                raw = text if isinstance(text, bytes) else text.encode("utf-8")
                path.write_bytes(raw)
                manifest = Manifest.load(base)
                self.assertEqual(manifest.items, {})
                self.assertIsNone(manifest.get("skill/alpha"))
                self.assertFalse(path.exists())
                backup = base / (MANIFEST_NAME + ".bak")
                self.assertEqual(backup.read_bytes(), raw)

    def test_item_values_must_be_objects(self) -> None:
        self.base.mkdir()
        path = self.base / MANIFEST_NAME
        path.write_text(
            json.dumps(
                {"schema": 1, "items": {"skill/alpha": {"mode": "copy"}, "skill/x": "junk"}}
            ),
            encoding="utf-8",
        )
        manifest = Manifest.load(self.base)
        self.assertEqual(manifest.items, {"skill/alpha": {"mode": "copy"}})
        self.assertTrue(path.exists())

    def test_save_creates_the_base_directory(self) -> None:
        base = self.root / "deep" / "nested" / "base"
        manifest = Manifest.load(base)
        self.record(manifest)
        manifest.save()
        self.assertTrue((base / MANIFEST_NAME).is_file())
        self.assertEqual(Manifest.load(base).get("skill/alpha")["hash"], "sha256:abc")

    def test_save_is_atomic(self) -> None:
        self.base.mkdir()
        manifest = Manifest.load(self.base)
        self.record(manifest, hash="sha256:one")
        manifest.save()
        path = self.base / MANIFEST_NAME

        seen = {}
        real_replace = os.replace

        def recording_replace(src: object, dst: object) -> object:
            seen["src"] = Path(src)
            seen["dst"] = Path(dst)
            seen["content"] = Path(src).read_text(encoding="utf-8")
            return real_replace(src, dst)

        with mock.patch("installer.state.os.replace", side_effect=recording_replace):
            self.record(manifest, hash="sha256:two")
            manifest.save()
        self.assertEqual(seen["src"].parent, self.base)
        self.assertEqual(seen["dst"], path)
        self.assertNotEqual(seen["src"].name, MANIFEST_NAME)
        self.assertEqual(json.loads(seen["content"])["items"]["skill/alpha"]["hash"], "sha256:two")
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), [MANIFEST_NAME])

        after = path.read_bytes()
        with mock.patch("installer.state.os.replace", side_effect=OSError("boom")):
            self.record(manifest, hash="sha256:three")
            with self.assertRaises(OSError):
                manifest.save()
        self.assertEqual(path.read_bytes(), after)
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), [MANIFEST_NAME])


class TargetPathTest(unittest.TestCase):
    def test_file_items_get_md_and_skills_do_not(self) -> None:
        base = Path("/tmp/fake-base")
        harness = make_harness(base)
        self.assertEqual(item_target(harness, "skill", "alpha"), base / "skills" / "alpha")
        self.assertEqual(item_target(harness, "agent", "helper"), base / "agents" / "helper.md")
        self.assertEqual(item_target(harness, "command", "alpha"), base / "commands" / "alpha.md")


class InstalledTest(unittest.TestCase):
    def test_key(self) -> None:
        installed = Installed(
            harness_id="opencode",
            kind="skill",
            name="alpha",
            target=Path("/tmp/fake-base/skills/alpha"),
            status=Status.NOT_INSTALLED,
            mode=None,
            installed_version=None,
            link_target=None,
            changed_files=(),
        )
        self.assertEqual(installed.key, "skill/alpha")


if __name__ == "__main__":
    unittest.main()
