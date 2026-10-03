"""Tests for scripts/validate.py, plus a check that this repository passes it."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "validate.py"

# Keep __pycache__ out of the skill folders, which get installed as symlinks.
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("validate", SCRIPT)
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)

GOOD_EVALS = {
    "skill_name": "demo",
    "evals": [{"id": 1, "prompt": "p", "expected_output": "o", "files": [], "expectations": ["e"]}],
    "trigger_evals": [
        {"query": "yes", "should_trigger": True},
        {"query": "no", "should_trigger": False},
    ],
}


class FixtureRepo:
    """A minimal valid toolkit with one skill, built in a temp folder."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.write_skill("demo", "Do the demo thing. Use when the user asks for a demo.", "# Demo\n\nBody.\n")
        self.write_evals("demo", GOOD_EVALS)
        (root / "agents").mkdir()
        validate.validate(root, fix=True)  # create the wrapper

    def write_skill(self, name: str, description: str, body: str, folder: str | None = None) -> Path:
        skill_dir = self.root / "skills" / (folder or name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "SKILL.md"
        path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}", encoding="utf-8")
        return path

    def write_evals(self, name: str, data: object) -> None:
        (self.root / "evals").mkdir(exist_ok=True)
        (self.root / "evals" / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


class ValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = FixtureRepo(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def errors(self) -> str:
        return "\n".join(validate.validate(self.repo.root).errors)

    def test_fixture_is_valid(self) -> None:
        report = validate.validate(self.repo.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_name_rules(self) -> None:
        self.repo.write_skill("Demo_Skill", "d", "body", folder="demo")
        errors = self.errors()
        self.assertIn("must match", errors)
        self.assertIn("does not match folder", errors)

    def test_missing_and_long_description(self) -> None:
        self.repo.write_skill("demo", "", "body")
        self.assertIn("missing description", self.errors())
        self.repo.write_skill("demo", "x" * 1025, "body")
        self.assertIn("max 1024", self.errors())

    def test_yaml_unsafe_description(self) -> None:
        for description, message in (
            ("Use when: the user asks", "contains ': '"),
            ("Review code #tags", "contains ' #'"),
            ("[draft] review code", "YAML indicator"),
            ("- review code", "YAML indicator"),
        ):
            with self.subTest(description=description):
                self.repo.write_skill("demo", description, "body")
                self.assertIn(message, self.errors())

    def test_quoted_description_is_allowed(self) -> None:
        self.repo.write_skill("demo", '"Use when: the user asks"', "body")
        validate.validate(self.repo.root, fix=True)
        self.assertEqual(self.errors(), "")

    def test_non_portable_frontmatter_key(self) -> None:
        path = self.repo.root / "skills" / "demo" / "SKILL.md"
        path.write_text(path.read_text().replace("---\n\n", "allowed-tools: Bash\n---\n\n", 1))
        self.assertIn("'allowed-tools' is not portable", self.errors())

    def test_nested_metadata_is_skipped(self) -> None:
        path = self.repo.root / "skills" / "demo" / "SKILL.md"
        path.write_text(path.read_text().replace("---\n\n", "metadata:\n  author: me\n---\n\n", 1))
        self.assertEqual(self.errors(), "")

    def test_missing_frontmatter_and_body(self) -> None:
        (self.repo.root / "skills" / "demo" / "SKILL.md").write_text("# no frontmatter\n")
        self.assertIn("missing or unterminated frontmatter", self.errors())
        self.repo.write_skill("demo", "Do the demo thing. Use when the user asks for a demo.", "")
        self.assertIn("empty body", self.errors())

    def test_missing_skill_md(self) -> None:
        (self.repo.root / "skills" / "other").mkdir()
        self.assertIn("missing SKILL.md", self.errors())

    def test_bundled_references(self) -> None:
        skill_dir = self.repo.root / "skills" / "demo"
        self.repo.write_skill(
            "demo",
            "Do the demo thing. Use when the user asks for a demo.",
            "Read `references/guide.md` and `references/themes/<theme>.md`.\n",
        )
        self.assertIn("references references/guide.md, which does not exist", self.errors())
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "guide.md").write_text("x")
        (skill_dir / "references" / "orphan.md").write_text("x")
        report = validate.validate(self.repo.root)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("orphan.md: bundled file not referenced" in w for w in report.warnings))

    def test_references_to_another_skills_files(self) -> None:
        self.repo.write_skill(
            "demo",
            "Do the demo thing. Use when the user asks for a demo.",
            "Load the `helper` skill first. Run `python3 <helper>/scripts/run.py` and read\n"
            "`<helper>/references/brief.md`; `<missing>/references/x.md` is a typo.\n",
        )
        helper = self.repo.write_skill("helper", "Help. Use when the demo needs help.", "Body.\n")
        (helper.parent / "scripts").mkdir()
        (helper.parent / "scripts" / "run.py").write_text("x")
        errors = self.errors()
        self.assertIn("references <helper>/references/brief.md, which does not exist", errors)
        self.assertIn("references <missing>/references/x.md, which does not exist", errors)
        self.assertNotIn("run.py", errors)

    def test_long_skill_warns(self) -> None:
        self.repo.write_skill("demo", "Do the demo thing. Use when the user asks for a demo.", "line\n" * 600)
        report = validate.validate(self.repo.root)
        self.assertEqual(report.errors, [])
        self.assertTrue(any("lines; move detail" in w for w in report.warnings))

    def test_wrapper_missing_outdated_and_fixed(self) -> None:
        wrapper = self.repo.root / "commands" / "demo.md"
        wrapper.unlink()
        self.assertIn("missing opencode wrapper", self.errors())
        validate.validate(self.repo.root, fix=True)
        self.assertEqual(self.errors(), "")
        self.repo.write_skill("demo", "A new description. Use when testing.", "body")
        self.assertIn("out of sync", self.errors())
        report = validate.validate(self.repo.root, fix=True)
        self.assertEqual(report.fixed, [str(wrapper)])
        self.assertIn("description: A new description. Use when testing.", wrapper.read_text())

    def test_not_user_invocable_has_no_wrapper(self) -> None:
        wrapper = self.repo.root / "commands" / "demo.md"
        path = self.repo.root / "skills" / "demo" / "SKILL.md"
        path.write_text(path.read_text().replace("---\n\n", "user-invocable: false\n---\n\n", 1))
        self.assertIn("not user-invocable and must not have a wrapper", self.errors())
        report = validate.validate(self.repo.root, fix=True)
        self.assertFalse(wrapper.exists())
        self.assertEqual(report.errors, [])
        path.write_text(path.read_text().replace("user-invocable: false", "user-invocable: no"))
        self.assertIn("user-invocable must be true or false", self.errors())

    def test_wrapper_for_unknown_skill(self) -> None:
        (self.repo.root / "commands" / "ghost.md").write_text(
            "---\ndescription: x\n---\n\nLoad and follow the `ghost` skill. $ARGUMENTS\n"
        )
        self.assertIn("wraps skill 'ghost', which does not exist", self.errors())

    def test_standalone_command_needs_description(self) -> None:
        (self.repo.root / "commands" / "standalone.md").write_text("Just a prompt.\n")
        self.assertIn("need frontmatter with a description", self.errors())

    def test_agents(self) -> None:
        agents = self.repo.root / "agents"
        (agents / "helper.md").write_text("---\nname: helper\ndescription: Helps.\n---\n\nYou help.\n")
        self.assertEqual(self.errors(), "")
        (agents / "nameless.md").write_text("---\ndescription: x\n---\n\nPrompt.\n")
        (agents / "empty.md").write_text("---\nname: empty\ndescription: x\n---\n")
        (agents / "claudy.md").write_text("---\nname: claudy\ndescription: x\ntools: Read\n---\n\nP\n")
        report = validate.validate(self.repo.root)
        errors = "\n".join(report.errors)
        self.assertIn("nameless.md: name must be present", errors)
        self.assertIn("empty.md: empty prompt", errors)
        self.assertTrue(any("'tools' is Claude-only" in w for w in report.warnings))

    def test_evals_missing_and_invalid(self) -> None:
        (self.repo.root / "evals" / "demo.json").unlink()
        self.assertIn("missing eval file", self.errors())
        (self.repo.root / "evals" / "demo.json").write_text("{not json")
        self.assertIn("invalid JSON", self.errors())

    def test_evals_schema(self) -> None:
        bad = {
            "skill_name": "other",
            "evals": [
                {"id": "1", "prompt": "", "expected_output": "o", "expectations": []},
                {"id": "1", "prompt": "p", "expected_output": "o", "expectations": ["e"], "files": [1]},
            ],
            "trigger_evals": [{"query": "only positives", "should_trigger": True}, {"query": "x"}],
        }
        self.repo.write_evals("demo", bad)
        errors = self.errors()
        for message in (
            "skill_name must be 'demo'",
            "id must be an integer",
            "prompt must be a non-empty string",
            "expectations must be a non-empty list",
            "files must be a list of strings",
            "eval ids must be unique",
            "boolean 'should_trigger'",
            "need both should_trigger true and false",
        ):
            self.assertIn(message, errors)

    def test_eval_for_unknown_skill(self) -> None:
        self.repo.write_evals("ghost", dict(GOOD_EVALS, skill_name="ghost"))
        self.assertIn("eval file for unknown skill 'ghost'", self.errors())


class RepositoryTest(unittest.TestCase):
    def test_this_repository_is_valid(self) -> None:
        report = validate.validate(REPO)
        self.assertEqual(report.errors, [], "\n".join(report.errors))

    def test_main_exit_code(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(validate.main(["--repo", str(REPO)]), 0)
        self.assertIn("ok:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
