"""Tests for scripts/installer/versions.py with throwaway git repositories."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent

sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "scripts"))

from installer import versions  # noqa: E402  (after sys.path)

GIT = shutil.which("git")
SKILL = "skills/demo/SKILL.md"


class GitFixture:
    """A throwaway repository where commits and tags are cheap."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.run("init", "--quiet")
        self.run("config", "user.name", "Installer Test")
        self.run("config", "user.email", "installer@example.com")

    def run(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8", "replace")

    def write(self, rel_path: str, text: str) -> Path:
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, message: str, rel_path: str = "f.txt", text: str = "content") -> str:
        self.write(rel_path, text)
        self.run("add", "-A")
        self.run("commit", "--quiet", "-m", message)
        return self.run("rev-parse", "--short", "HEAD").strip()

    def tag(self, name: str) -> None:
        self.run("tag", name)


@unittest.skipUnless(GIT, "git is required for these tests")
class VersionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)

        # A fake HOME so git never reads or writes the real user's config.
        self.home = self.root / "home"
        self.home.mkdir()
        patch = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        patch.start()
        self.addCleanup(patch.stop)

        self.repo_dir = self.root / "repo"
        self.repo_dir.mkdir()
        self.git = GitFixture(self.repo_dir)

    def build_tagged(self) -> str:
        """v0.1.0, a change to the demo skill tagged 2026.10.01.1, then 2026.10.03.2."""
        self.git.commit("initial", "f.txt", "one")
        self.git.tag("v0.1.0")
        demo_commit = self.git.commit("change the demo skill", SKILL, "v1\n")
        self.git.tag("2026.10.01.1")
        self.git.commit("other change", "f.txt", "two")
        self.git.tag("2026.10.03.2")
        return demo_commit

    def with_upstream(self) -> None:
        """Push the tagged history to a local origin and reset HEAD one release back."""
        self.build_tagged()
        origin = self.root / "origin.git"
        subprocess.run([GIT, "init", "--bare", "--quiet", str(origin)], capture_output=True, check=True)
        self.git.run("remote", "add", "origin", str(origin))
        branch = self.git.run("symbolic-ref", "--short", "HEAD").strip()
        self.git.run("push", "--quiet", "--set-upstream", "origin", branch, "--tags")
        self.git.run("reset", "--hard", "2026.10.01.1")

    def plain_dir(self) -> Path:
        path = self.root / "plain"
        path.mkdir()
        (path / "notes.txt").write_text("not a repository", encoding="utf-8")
        return path

    def test_release_key_is_numeric(self) -> None:
        self.assertGreater(
            versions.release_key("2026.10.03.10"),
            versions.release_key("2026.10.03.9"),
        )
        self.assertEqual(versions.release_key("2026.10.01.1"), (2026, 10, 1, 1))
        tags = ["2026.10.03.2", "2026.10.01.1", "2026.10.03.10"]
        self.assertEqual(
            sorted(tags, key=versions.release_key),
            ["2026.10.01.1", "2026.10.03.2", "2026.10.03.10"],
        )

    def test_tagged_label_ignores_other_tags(self) -> None:
        self.build_tagged()
        version = versions.toolkit_version(self.repo_dir)
        self.assertEqual(version.tag, "2026.10.03.2")
        self.assertEqual(version.ahead, 0)
        self.assertFalse(version.dirty)
        self.assertEqual(version.commit, self.git.run("rev-parse", "--short", "HEAD").strip())
        self.assertEqual(version.label, "2026.10.03.2")
        self.assertIn("v0.1.0", self.git.run("tag").splitlines())

    def test_ahead_label(self) -> None:
        self.build_tagged()
        self.git.commit("more work", "f.txt", "three")
        version = versions.toolkit_version(self.repo_dir)
        self.assertEqual(version.tag, "2026.10.03.2")
        self.assertEqual(version.ahead, 1)
        self.assertEqual(version.label, "2026.10.03.2+1")

    def test_dirty_label(self) -> None:
        self.build_tagged()
        self.git.write("f.txt", "edited but not committed")
        version = versions.toolkit_version(self.repo_dir)
        self.assertTrue(version.dirty)
        self.assertEqual(version.label, "2026.10.03.2 (modified)")

    def test_no_tags_label(self) -> None:
        sha = self.git.commit("only commit", "f.txt", "x")
        version = versions.toolkit_version(self.repo_dir)
        self.assertIsNone(version.tag)
        self.assertEqual(version.commit, sha)
        self.assertFalse(version.dirty)
        self.assertEqual(version.label, f"dev ({sha})")

    def test_no_git_label(self) -> None:
        version = versions.toolkit_version(self.plain_dir())
        self.assertIsNone(version.tag)
        self.assertIsNone(version.commit)
        self.assertFalse(version.dirty)
        self.assertEqual(version.label, "unknown")

    def test_item_version_uses_the_oldest_release(self) -> None:
        demo_commit = self.build_tagged()
        version = versions.item_version(self.repo_dir, "skills/demo")
        self.assertEqual(version.release, "2026.10.01.1")
        self.assertEqual(version.commit, demo_commit)
        self.assertEqual(version.subject, "change the demo skill")
        self.assertRegex(version.date, r"^\d{4}-\d{2}-\d{2}$")
        self.assertFalse(version.local_changes)
        self.assertEqual(version.label, "2026.10.01.1")

    def test_item_version_unreleased_when_no_release_contains_it(self) -> None:
        self.build_tagged()
        self.git.commit("change the demo again", SKILL, "v2\n")
        version = versions.item_version(self.repo_dir, "skills/demo")
        self.assertIsNone(version.release)
        self.assertTrue(version.commit)
        self.assertFalse(version.local_changes)
        self.assertEqual(version.label, "unreleased")

    def test_item_version_local_changes(self) -> None:
        self.build_tagged()
        self.git.write(SKILL, "edited but not committed\n")
        version = versions.item_version(self.repo_dir, "skills/demo")
        self.assertTrue(version.local_changes)
        self.assertEqual(version.release, "2026.10.01.1")
        self.assertEqual(version.label, "2026.10.01.1+local")

    def test_item_version_is_memoised_per_path(self) -> None:
        self.build_tagged()
        first = versions.item_version(self.repo_dir, "skills/demo")
        self.assertIs(versions.item_version(self.repo_dir, "skills/demo"), first)
        versions.clear_cache()
        self.assertIsNot(versions.item_version(self.repo_dir, "skills/demo"), first)

    def test_item_version_without_git(self) -> None:
        version = versions.item_version(self.plain_dir(), "skills/demo")
        self.assertIsNone(version.release)
        self.assertIsNone(version.commit)
        self.assertIsNone(version.date)
        self.assertIsNone(version.subject)
        self.assertFalse(version.local_changes)
        self.assertEqual(version.label, "unreleased")

    def test_latest_remote_release_without_remote(self) -> None:
        self.build_tagged()
        self.assertIsNone(versions.latest_remote_release(self.repo_dir, timeout=5))
        self.assertIsNone(versions.latest_remote_release(self.plain_dir(), timeout=5))

    def test_latest_remote_release_from_a_local_origin(self) -> None:
        self.build_tagged()
        origin = self.root / "origin.git"
        subprocess.run([GIT, "init", "--bare", "--quiet", str(origin)], capture_output=True, check=True)
        self.git.run("remote", "add", "origin", str(origin))
        self.git.run("push", "--quiet", "origin", "HEAD:refs/heads/main")
        self.git.run("push", "--quiet", "origin", "--tags")
        self.assertEqual(versions.latest_remote_release(self.repo_dir, timeout=10), "2026.10.03.2")

    def test_pull_status_without_upstream(self) -> None:
        self.build_tagged()
        can_pull, reason = versions.pull_status(self.repo_dir)
        self.assertFalse(can_pull)
        self.assertTrue(reason)

    def test_pull_status_and_pull_when_upstream_is_ahead(self) -> None:
        self.with_upstream()
        can_pull, reason = versions.pull_status(self.repo_dir)
        self.assertTrue(can_pull, reason)
        ok, output = versions.pull(self.repo_dir)
        self.assertTrue(ok, output)
        self.assertEqual(versions.toolkit_version(self.repo_dir).tag, "2026.10.03.2")
        can_pull, reason = versions.pull_status(self.repo_dir)
        self.assertFalse(can_pull)
        self.assertTrue(reason)

    def test_pull_status_refuses_a_dirty_tree(self) -> None:
        self.with_upstream()
        self.git.write("f.txt", "edited but not committed")
        can_pull, reason = versions.pull_status(self.repo_dir)
        self.assertFalse(can_pull)
        self.assertIn("uncommitted", reason)

    def test_pull_status_refuses_diverged_branches(self) -> None:
        self.with_upstream()
        self.git.commit("local only", "local.txt", "local")
        can_pull, reason = versions.pull_status(self.repo_dir)
        self.assertFalse(can_pull)
        self.assertIn("diverged", reason)

    def test_pull_status_without_git(self) -> None:
        can_pull, reason = versions.pull_status(self.plain_dir())
        self.assertFalse(can_pull)
        self.assertTrue(reason)

    def test_pull_failure_is_reported(self) -> None:
        ok, message = versions.pull(self.plain_dir())
        self.assertFalse(ok)
        self.assertTrue(message)


if __name__ == "__main__":
    unittest.main()
