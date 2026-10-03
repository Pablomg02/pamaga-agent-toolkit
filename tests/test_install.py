"""Tests for scripts/install.sh, run against a throwaway HOME."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "install.sh"


@unittest.skipUnless(shutil.which("bash"), "bash is required")
class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.claude = self.home / ".claude"
        self.opencode = self.home / ".config" / "opencode"
        self.skills = sorted(p.name for p in (REPO / "skills").iterdir() if p.is_dir())
        self.commands = sorted(p.name for p in (REPO / "commands").glob("*.md"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_install(self, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        env["HOME"] = str(self.home)
        return subprocess.run(
            ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
        )

    def linked(self, folder: Path) -> list[str]:
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_symlink())

    def test_claude_gets_skills_but_no_command_wrappers(self) -> None:
        result = self.run_install("claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.linked(self.claude / "skills"), self.skills)
        self.assertEqual(self.linked(self.claude / "commands"), [])
        for name in self.skills:
            target = (self.claude / "skills" / name).resolve()
            self.assertEqual(target, (REPO / "skills" / name).resolve())

    def test_opencode_gets_skills_and_wrappers(self) -> None:
        result = self.run_install("opencode")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.linked(self.opencode / "skills"), self.skills)
        self.assertEqual(self.linked(self.opencode / "commands"), self.commands)
        self.assertFalse((self.claude / "skills").exists())

    def test_install_is_idempotent_and_uninstall_cleans_up(self) -> None:
        self.run_install("all")
        second = self.run_install("all")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn("link ", second.stdout)
        self.assertIn("ok ", second.stdout)

        removed = self.run_install("--uninstall", "all")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        for folder in (self.claude, self.opencode):
            for sub in ("skills", "agents", "commands"):
                self.assertEqual(self.linked(folder / sub), [], f"{folder / sub}")

    def test_uninstall_removes_wrappers_linked_by_older_versions(self) -> None:
        commands = self.claude / "commands"
        commands.mkdir(parents=True)
        for name in self.commands:
            (commands / name).symlink_to(REPO / "commands" / name)
        self.run_install("--uninstall", "claude")
        self.assertEqual(self.linked(commands), [])

    def test_never_touches_foreign_files(self) -> None:
        skills = self.claude / "skills"
        own = skills / self.skills[0]
        own.mkdir(parents=True)
        (own / "SKILL.md").write_text("mine")
        foreign_link = skills / "elsewhere"
        foreign_link.symlink_to(self.home)

        result = self.run_install("claude")
        self.assertIn("SKIP", result.stderr)
        self.assertEqual((own / "SKILL.md").read_text(), "mine")

        self.run_install("--uninstall", "claude")
        self.assertTrue(own.is_dir())
        self.assertTrue(foreign_link.is_symlink())

    def test_rejects_unknown_arguments(self) -> None:
        result = self.run_install("vim")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unknown argument", result.stderr)


if __name__ == "__main__":
    unittest.main()
