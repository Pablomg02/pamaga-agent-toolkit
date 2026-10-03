"""Tests for scripts/next_release.py with throwaway git repositories."""

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

import next_release  # noqa: E402  (after sys.path)

GIT = shutil.which("git")


class BumpTest(unittest.TestCase):
    def test_first_release(self) -> None:
        self.assertEqual(next_release.bump(None, ["anything [patch]"]), "0.1.0")

    def test_minor_by_default(self) -> None:
        self.assertEqual(next_release.bump("0.3.2", ["add a skill", "fix docs"]), "0.4.0")

    def test_patch_marker_any_case_anywhere(self) -> None:
        self.assertEqual(next_release.bump("0.3.2", ["add a skill", "Fix typo [Patch]"]), "0.3.3")

    def test_no_commits_is_still_minor(self) -> None:
        self.assertEqual(next_release.bump("0.9.0", []), "0.10.0")


@unittest.skipUnless(GIT, "git is required for these tests")
class NextReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        home = self.root / "home"
        home.mkdir()
        patch = mock.patch.dict(
            os.environ,
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Release Test")
        self.git("config", "user.email", "release@example.com")

    def git(self, *args: str) -> str:
        return next_release.git(self.repo, *args)

    def commit(self, message: str) -> None:
        self.git("commit", "--quiet", "--allow-empty", "-m", message)

    def release(self) -> str | None:
        tag = next_release.next_release(self.repo)
        if tag:
            self.git("tag", tag)
        return tag

    def test_sequence_of_releases(self) -> None:
        self.commit("initial")
        self.assertEqual(self.release(), "0.1.0")
        self.commit("fix a typo [patch]")
        self.assertEqual(self.release(), "0.1.1")
        self.commit("add a skill")
        self.assertEqual(self.release(), "0.2.0")

    def test_patch_marker_only_counts_since_last_release(self) -> None:
        self.commit("old fix [patch]")
        self.assertEqual(self.release(), "0.1.0")
        self.commit("add a skill")
        self.assertEqual(self.release(), "0.2.0")

    def test_numeric_order_and_foreign_tags(self) -> None:
        self.commit("initial")
        self.git("tag", "0.9.0")
        self.commit("more")
        self.git("tag", "0.10.0")
        self.git("tag", "v5.0.0")
        self.git("tag", "2026.10.03.1")
        self.commit("next")
        self.assertEqual(next_release.next_release(self.repo), "0.11.0")

    def test_released_head_gives_nothing(self) -> None:
        self.commit("initial")
        self.release()
        self.assertIsNone(next_release.next_release(self.repo))

    def test_commit_older_than_the_last_release_gives_nothing(self) -> None:
        # Two pushes to main whose CI finishes out of order: the newer one is
        # released first, and the older one must not get a higher version.
        self.commit("initial")
        self.release()
        self.commit("older push")
        older = self.git("rev-parse", "HEAD").strip()
        self.commit("newer push")
        self.assertEqual(self.release(), "0.2.0")
        self.git("checkout", "--quiet", older)
        self.assertIsNone(next_release.next_release(self.repo))

    def test_patch_marker_on_a_merged_branch_counts(self) -> None:
        # Releases come from "Merge pull request ... from dev" commits; the
        # [patch] marker is on the merged dev commit, not on the merge.
        self.commit("initial")
        self.release()
        main = self.git("rev-parse", "--abbrev-ref", "HEAD").strip()
        self.git("switch", "--quiet", "-c", "dev")
        self.commit("fix typo [patch]")
        self.git("switch", "--quiet", main)
        self.git("merge", "--quiet", "--no-ff", "dev", "-m", "Merge pull request #1 from x/dev")
        notes = next_release.release_notes(self.repo)
        self.assertEqual(next_release.next_release(self.repo), "0.1.1")
        self.assertIn("- fix typo [patch] (", notes)
        self.assertNotIn("Merge pull request", notes)

    def test_notes_list_commits_since_last_release(self) -> None:
        self.commit("before")
        self.release()
        self.commit("feature one")
        self.commit("feature two")
        notes = next_release.release_notes(self.repo)
        self.assertIn("- feature one (", notes)
        self.assertIn("- feature two (", notes)
        self.assertNotIn("before", notes)

    def test_cli_prints_tag_and_writes_notes(self) -> None:
        self.commit("initial")
        notes = self.root / "notes.md"
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "next_release.py"), "--repo", str(self.repo), "--notes", str(notes)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "0.1.0")
        self.assertIn("- initial (", notes.read_text(encoding="utf-8"))

    def test_git_failure_raises(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        with self.assertRaises(subprocess.CalledProcessError):
            next_release.next_release(plain)


if __name__ == "__main__":
    unittest.main()
