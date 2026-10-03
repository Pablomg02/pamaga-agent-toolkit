"""Tests for skills/concurrent-work/scripts/work.py, using real git repositories."""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills" / "concurrent-work" / "scripts" / "work.py"

# Keep __pycache__ out of the skill folders, which get installed as symlinks.
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("work", SCRIPT)
work = importlib.util.module_from_spec(spec)
spec.loader.exec_module(work)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "LC_ALL": "C",  # git messages in English, whatever the machine locale
}


class OverlapTest(unittest.TestCase):
    def test_overlaps(self) -> None:
        cases = [
            ("src/auth/**", "src/auth/login.py", True),
            ("src/auth/login.py", "src/auth/login.py", True),
            ("src/auth/**", "src/export/**", False),
            ("src/a/**", "src/ab/**", False),
            ("src/*.py", "src/auth/x.py", True),
            ("**", "anything/at/all", True),
            ("docs/README.md", "docs/INSTALL.md", False),
            ("src", "src/auth/x.py", True),
        ]
        for a, b, expected in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(work.overlaps(a, b), expected)
                self.assertEqual(work.overlaps(b, a), expected)

    def test_conflicts_ignore_finished_work(self) -> None:
        others = [
            {"slug": "a", "status": "working", "paths": "src/auth/**, docs/auth.md"},
            {"slug": "b", "status": "finished", "paths": "src/export/**"},
        ]
        self.assertEqual(
            work.conflicts(["src/auth/x.py", "src/export/y.py"], others),
            [("a", "src/auth/x.py", "src/auth/**")],
        )

    def test_staleness(self) -> None:
        at = datetime.datetime(2026, 10, 3, 12, 0, tzinfo=datetime.timezone.utc)
        fresh = {"status": "working", "updated": "2026-10-03T11:00:00+00:00"}
        old = {"status": "working", "updated": "2026-10-03T09:00:00+00:00"}
        old_finished = {"status": "finished", "updated": "2026-10-03T09:00:00+00:00"}
        broken = {"status": "working", "updated": "yesterday"}
        self.assertFalse(work.is_stale(fresh, at))
        self.assertTrue(work.is_stale(old, at))
        self.assertFalse(work.is_stale(old_finished, at))
        self.assertTrue(work.is_stale(broken, at))
        self.assertEqual(work.age(fresh, at), "60 min ago")
        self.assertEqual(work.age(old, at), "3 h ago")


@unittest.skipUnless(shutil.which("git"), "git is required")
class WorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.main = self.base / "app"
        self.main.mkdir()
        self._env = {k: os.environ.get(k) for k in GIT_ENV}
        os.environ.update(GIT_ENV)
        self.git("init", "-q", "-b", "main")
        (self.main / "README.md").write_text("hello\n")
        self.git("add", "README.md")
        self.git("commit", "-q", "-m", "init")
        self._cwd = os.getcwd()
        os.chdir(self.main)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd or self.main, capture_output=True, text=True, check=True
        ).stdout.strip()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = work.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def start(self, slug: str, paths: str, *extra: str) -> Path:
        code, out, err = self.run_cli("start", slug, "--task", f"Task {slug}", "--paths", paths, *extra)
        self.assertEqual(code, 0, out + err)
        return self.base / "app-work" / slug

    def test_empty_board(self) -> None:
        self.assertIn("board is empty", self.run_cli("list")[1])

    def test_start_creates_note_branch_and_worktree(self) -> None:
        worktree = self.start("fix-export", "src/export/**", "--expect", "export() returns []")
        self.assertTrue((worktree / "README.md").is_file())
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=worktree), "work/fix-export")
        note = work.read_note(self.main / ".git" / "agent-work" / "fix-export.md")
        self.assertEqual(note["status"], "working")
        self.assertEqual(note["base"], "main")
        self.assertEqual(note["paths"], "src/export/**")
        self.assertEqual(note["worktree"], str(worktree))
        self.assertEqual(note["expect"], "export() returns []")
        out = self.run_cli("list")[1]
        self.assertIn("fix-export  [working]", out)
        self.assertIn("expect: export() returns []", out)
        self.assertEqual(self.git("status", "--porcelain"), "")  # main folder untouched

    def test_overlap_stops_without_side_effects(self) -> None:
        self.start("auth", "src/auth/**")
        code, out, _ = self.run_cli("start", "login", "--task", "x", "--paths", "src/auth/login.py")
        self.assertEqual(code, 2)
        self.assertIn("src/auth/login.py  vs  src/auth/**  (auth)", out)
        self.assertFalse((self.main / ".git" / "agent-work" / "login.md").exists())
        self.assertNotIn("work/login", self.git("branch"))
        self.start("login", "src/auth/login.py", "--allow-overlap")

    def test_duplicate_slug_and_invalid_input(self) -> None:
        self.start("auth", "src/auth/**")
        code, _, err = self.run_cli("start", "auth", "--task", "x", "--paths", "docs/**")
        self.assertEqual(code, 1)
        self.assertIn("already on the board", err)
        code, _, err = self.run_cli("start", "Bad Slug", "--task", "x", "--paths", "a")
        self.assertIn("invalid slug", err)
        code, _, err = self.run_cli("start", "ok", "--task", "x", "--paths", " , ")
        self.assertIn("--paths needs at least one path", err)

    def test_failed_worktree_removes_note(self) -> None:
        self.git("branch", "work/taken")
        code, _, err = self.run_cli("start", "taken", "--task", "x", "--paths", "a/**")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertFalse((self.main / ".git" / "agent-work" / "taken.md").exists())

    def test_ping_from_inside_worktree(self) -> None:
        worktree = self.start("auth", "src/auth/**")
        os.chdir(worktree)
        code, out, _ = self.run_cli("ping", "auth", "--progress", "T1 done")
        self.assertEqual(code, 0)
        self.run_cli("ping", "auth", "--status", "finished")
        note = work.read_note(self.main / ".git" / "agent-work" / "auth.md")
        self.assertEqual((note["status"], note["progress"]), ("finished", "T1 done"))
        self.assertEqual(self.run_cli("ping", "ghost")[0], 1)

    def test_list_marks_stale_notes(self) -> None:
        self.start("auth", "src/auth/**")
        path = self.main / ".git" / "agent-work" / "auth.md"
        note = work.read_note(path)
        note["updated"] = "2020-01-01T00:00:00+00:00"
        work.write_note(path, note)
        self.assertIn("STALE", self.run_cli("list")[1])

    def test_end_after_merge_cleans_everything(self) -> None:
        worktree = self.start("feature", "src/**")
        (worktree / "new.txt").write_text("x\n")
        self.git("add", "new.txt", cwd=worktree)
        self.git("commit", "-q", "-m", "feature", cwd=worktree)
        self.git("merge", "-q", "--ff-only", "work/feature")

        code, out, _ = self.run_cli("end", "feature")
        self.assertEqual(code, 0, out)
        self.assertIn("deleted branch work/feature", out)
        self.assertFalse(worktree.exists())
        self.assertFalse((self.base / "app-work").exists())
        self.assertNotIn("work/feature", self.git("branch"))
        self.assertIn("board is empty", self.run_cli("list")[1])

    def test_end_keeps_unmerged_work_unless_forced(self) -> None:
        worktree = self.start("feature", "src/**")
        (worktree / "new.txt").write_text("x\n")
        self.git("add", "new.txt", cwd=worktree)
        self.git("commit", "-q", "-m", "feature", cwd=worktree)
        (worktree / "dirty.txt").write_text("uncommitted\n")

        code, _, err = self.run_cli("end", "feature")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes", err)
        self.assertTrue(worktree.exists())
        self.assertTrue((self.main / ".git" / "agent-work" / "feature.md").exists())

        (worktree / "dirty.txt").unlink()
        code, out, _ = self.run_cli("end", "feature")
        self.assertEqual(code, 0)
        self.assertIn("kept branch work/feature: it is not merged", out)
        self.assertIn("work/feature", self.git("branch"))

    def test_end_force_discards(self) -> None:
        worktree = self.start("spike", "src/**")
        (worktree / "dirty.txt").write_text("x\n")
        code, out, _ = self.run_cli("end", "spike", "--force")
        self.assertEqual(code, 0, out)
        self.assertFalse(worktree.exists())
        self.assertNotIn("work/spike", self.git("branch"))

    def test_end_refuses_from_inside_the_worktree(self) -> None:
        worktree = self.start("auth", "src/auth/**")
        os.chdir(worktree)
        code, _, err = self.run_cli("end", "auth")
        self.assertEqual(code, 1)
        self.assertIn("run this from outside", err)


if __name__ == "__main__":
    unittest.main()
