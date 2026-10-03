"""Tests for scripts/install.py and the install.sh shim (non-interactive paths)."""

from __future__ import annotations

import json
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "install.py"
SHIM = REPO / "scripts" / "install.sh"


def env_for(home: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if key not in ("XDG_CONFIG_HOME", "PAMAGA_OFFLINE")}
    env["HOME"] = str(home)
    env["NO_COLOR"] = "1"
    return env


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.opencode = self.home / ".config" / "opencode"
        self.claude = self.home / ".claude"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=REPO,
            env=env_for(self.home),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def run_shim(self, *args: str, **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SHIM), *args],
            cwd=REPO,
            env=env_for(self.home),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
            **kwargs,
        )

    def status(self, harness: str = "opencode") -> dict:
        result = self.run_cli("--status", "--json", "--harness", harness, "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def linked(self, folder: Path) -> list:
        if not folder.is_dir():
            return []
        return sorted(path.name for path in folder.iterdir() if path.is_symlink())


class InstallCliTest(CliTest):
    def test_yes_with_a_subset_links_only_the_closure(self) -> None:
        result = self.run_cli("--yes", "--harness", "opencode", "--skills", "make-plan", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.linked(self.opencode / "skills"),
            ["make-plan", "plans-convention", "research-topic"],
        )
        self.assertEqual(self.linked(self.opencode / "commands"), ["make-plan.md", "research-topic.md"])
        self.assertFalse(self.claude.exists())

    def test_copy_status_modified_skip_and_force(self) -> None:
        args = ("--yes", "--harness", "opencode", "--skills", "make-plan", "--mode", "copy", "--offline")
        self.assertEqual(self.run_cli(*args).returncode, 0)
        copied = self.opencode / "skills" / "make-plan"
        self.assertTrue(copied.is_dir())
        self.assertFalse(copied.is_symlink())
        self.assertEqual(
            self.status()["harnesses"]["opencode"]["skill/make-plan"]["status"], "up-to-date"
        )

        skill_md = copied / "SKILL.md"
        skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\nedited by the test\n", encoding="utf-8")
        self.assertEqual(
            self.status()["harnesses"]["opencode"]["skill/make-plan"]["status"], "modified"
        )

        skipped = self.run_cli(*args)
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        self.assertIn("SKIP", skipped.stderr)
        self.assertIn("edited by the test", skill_md.read_text(encoding="utf-8"))

        forced = self.run_cli(*args, "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("Backups kept in:", forced.stdout)
        backups = list((self.opencode / ".pamaga-backups").glob("*/skills/make-plan"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(
            self.status()["harnesses"]["opencode"]["skill/make-plan"]["status"], "up-to-date"
        )

    def test_prune_removes_managed_items_not_selected(self) -> None:
        self.assertEqual(self.run_cli("--yes", "--harness", "opencode", "--offline").returncode, 0)
        self.assertTrue((self.opencode / "skills" / "find-bug").exists())
        result = self.run_cli(
            "--yes", "--harness", "opencode", "--skills", "make-plan", "--prune", "--offline"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.opencode / "skills" / "find-bug").exists())
        self.assertTrue((self.opencode / "skills" / "make-plan").exists())
        self.assertTrue((self.opencode / "skills" / "research-topic").exists())

    def test_uninstall_removes_links_and_copies(self) -> None:
        self.run_cli("--yes", "--harness", "opencode", "--skills", "make-plan", "--offline")
        self.run_cli(
            "--yes", "--harness", "opencode", "--skills", "find-bug", "--mode", "copy", "--offline"
        )
        result = self.run_cli("--uninstall", "--harness", "opencode", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.linked(self.opencode / "skills"), [])
        self.assertFalse((self.opencode / "skills" / "find-bug").exists())

    def test_status_plain_table(self) -> None:
        self.run_cli("--yes", "--harness", "opencode", "--skills", "make-plan", "--offline")
        result = self.run_cli("--status", "--harness", "opencode", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("item", result.stdout)
        self.assertIn("skill/make-plan", result.stdout)

    def test_version_prints_a_release_label(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        label = result.stdout.strip()
        self.assertTrue(label, "empty --version output")
        self.assertTrue(
            re.match(r"^\d{4}\.\d{2}\.\d{2}\.\d+(\+\d+)?( \(modified\))?$", label) or label.startswith("dev ("),
            label,
        )

    def test_no_tty_and_no_flags_prints_usage_and_exits_two(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)

    def test_unknown_skill_is_rejected(self) -> None:
        result = self.run_cli("--yes", "--skills", "does-not-exist", "--offline")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown skill", result.stderr)


class UpdateCliTest(CliTest):
    def manifest(self, base: Path) -> dict:
        return json.loads((base / ".pamaga-toolkit.json").read_text(encoding="utf-8"))

    def test_update_with_nothing_installed_does_nothing(self) -> None:
        result = self.run_cli("--update", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Nothing from the toolkit is installed yet", result.stdout)
        self.assertFalse((self.claude / "skills").exists())
        self.assertFalse((self.opencode / "skills").exists())

    def test_update_refreshes_outdated_copies_only_where_installed(self) -> None:
        self.run_cli("--yes", "--harness", "claude", "--skills", "make-plan", "--mode", "copy",
                     "--offline")
        # Pretend the copy came from an older release: the files differ from
        # the source and the manifest recorded exactly those files.
        skill_md = self.claude / "skills" / "make-plan" / "SKILL.md"
        skill_md.write_text("older release\n", encoding="utf-8")
        sys.path.insert(0, str(REPO / "scripts"))
        from installer.catalog import content_hash

        manifest = self.manifest(self.claude)
        manifest["items"]["skill/make-plan"]["hash"] = content_hash(self.claude / "skills" / "make-plan")
        (self.claude / ".pamaga-toolkit.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.status("claude")["harnesses"]["claude"]["skill/make-plan"]["status"],
                         "outdated")

        result = self.run_cli("--update", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update", result.stdout)
        self.assertEqual(skill_md.read_text(encoding="utf-8"),
                         (REPO / "skills" / "make-plan" / "SKILL.md").read_text(encoding="utf-8"))
        statuses = self.status("claude")["harnesses"]["claude"]
        self.assertEqual(statuses["skill/make-plan"]["status"], "up-to-date")
        # Nothing new was installed: not other skills, not other harnesses.
        self.assertEqual(statuses["skill/find-bug"]["status"], "not-installed")
        self.assertFalse((self.opencode / "skills").exists())
        self.assertFalse(list((self.claude / "skills").glob(".*pamaga*")))

    def test_update_skips_local_edits_unless_forced(self) -> None:
        self.run_cli("--yes", "--harness", "claude", "--skills", "make-plan", "--mode", "copy",
                     "--offline")
        skill_md = self.claude / "skills" / "make-plan" / "SKILL.md"
        skill_md.write_text("my notes\n", encoding="utf-8")
        result = self.run_cli("--update", "--offline")
        self.assertIn("SKIP", result.stderr)
        self.assertIn("--force", result.stderr)
        self.assertIn("Nothing updated", result.stdout)
        self.assertEqual(skill_md.read_text(encoding="utf-8"), "my notes\n")

    def test_update_keeps_each_item_in_its_mode(self) -> None:
        self.run_cli("--yes", "--harness", "opencode", "--skills", "find-bug", "--offline")
        self.run_cli("--yes", "--harness", "opencode", "--skills", "make-plan", "--mode", "copy",
                     "--offline")
        result = self.run_cli("--update", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.opencode / "skills" / "find-bug").is_symlink())
        copied = self.opencode / "skills" / "make-plan"
        self.assertTrue(copied.is_dir() and not copied.is_symlink())

    def test_update_removes_links_to_skills_gone_from_the_toolkit(self) -> None:
        self.run_cli("--yes", "--harness", "opencode", "--skills", "find-bug", "--offline")
        gone = self.opencode / "skills" / "gone-skill"
        os.symlink(REPO / "skills" / "gone-skill", gone)
        result = self.run_cli("--update", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(gone))
        self.assertTrue((self.opencode / "skills" / "find-bug").is_symlink())

    def test_pull_that_is_not_possible_still_updates(self) -> None:
        self.run_cli("--yes", "--harness", "opencode", "--skills", "find-bug", "--offline")
        env = env_for(self.home)
        env["GIT_DIR"] = str(self.home / "not-a-repo")  # git fails: pulling is not possible
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--update", "--pull"],
            cwd=REPO, env={**env, "PAMAGA_OFFLINE": ""}, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Not pulling", result.stdout)
        self.assertIn("up to date", result.stdout)

    def test_pull_needs_yes_or_update(self) -> None:
        result = self.run_cli("--status", "--pull", "--offline")
        self.assertEqual(result.returncode, 2)

    def test_hand_made_identical_copy_is_adopted(self) -> None:
        import shutil

        shutil.copytree(REPO / "skills" / "find-bug", self.claude / "skills" / "find-bug")
        result = self.run_cli("--yes", "--harness", "claude", "--skills", "find-bug", "--mode",
                              "copy", "--offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill/find-bug", self.manifest(self.claude)["items"])
        # Uninstall leaves a hand-made copy alone only while it is unrecorded;
        # once adopted it is ours and goes away with the rest.
        self.run_cli("--uninstall", "--harness", "claude", "--offline")
        self.assertFalse((self.claude / "skills" / "find-bug").exists())

    def test_uninstall_keeps_unrecorded_identical_copy(self) -> None:
        import shutil

        shutil.copytree(REPO / "skills" / "find-bug", self.claude / "skills" / "find-bug")
        self.run_cli("--uninstall", "--harness", "claude", "--offline")
        self.assertTrue((self.claude / "skills" / "find-bug" / "SKILL.md").is_file())


class ShimTest(CliTest):
    def test_shim_without_a_tty_keeps_the_opencode_default(self) -> None:
        result = self.run_shim()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("make-plan", self.linked(self.opencode / "skills"))
        self.assertIn("find-bug", self.linked(self.opencode / "skills"))

    def test_shim_unknown_argument(self) -> None:
        result = self.run_shim("vim")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Unknown argument: vim", result.stderr)

    @unittest.skipUnless(hasattr(pty, "openpty") and os.name == "posix", "pty is POSIX-only")
    def test_shim_in_a_tty_starts_the_tui_and_quits(self) -> None:
        master, slave = pty.openpty()
        env = env_for(self.home)
        env["PAMAGA_OFFLINE"] = "1"  # tests never touch the network
        process = subprocess.Popen(
            ["bash", str(SHIM)],
            cwd=REPO,
            env=env,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)
        output = b""

        def drain(seconds: float) -> None:
            # Keep reading so the TUI never blocks on a full pty buffer.
            nonlocal output
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and process.poll() is None:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        output += os.read(master, 65536)
                    except OSError:  # Linux: EIO once the child is gone
                        return

        try:
            # Send "q" only once the first frame (and its key hints) is drawn.
            deadline = time.monotonic() + 15
            while b"quit" not in output and time.monotonic() < deadline and process.poll() is None:
                drain(0.2)
            os.write(master, b"q")
            drain(15)
            code = process.wait(timeout=5)
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
        self.assertEqual(code, 0, output.decode("utf-8", "replace")[-2000:])


if __name__ == "__main__":
    unittest.main()
