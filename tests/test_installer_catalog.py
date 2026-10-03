"""Tests for scripts/installer/catalog.py, against this repo and crafted folders."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Keep __pycache__ out of the skill folders, which get installed as symlinks.
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "scripts"))

from installer import catalog  # noqa: E402  (after sys.path)

# The dependencies described in plans/in-progress/0001-interactive-installer/plan.md.
EXPECTED_REQUIRES = {
    "deep-review": set(),
    "find-bug": set(),
    "implement-plan": {"plans-convention"},
    "make-plan": {"plans-convention", "research-topic"},
    "make-roadmap": {"plans-convention"},
    "new-ticket": {"plans-convention"},
    "plan-page": {"plans-convention"},
    "plans-convention": set(),
    "research-topic": {"plans-convention"},
    "save-learning": set(),
    "ship-work": {"plans-convention"},
}

EXPECTED_SKILL_ORDER = [
    "research-topic",
    "make-roadmap",
    "make-plan",
    "new-ticket",
    "plan-page",
    "implement-plan",
    "find-bug",
    "deep-review",
    "ship-work",
    "save-learning",
    "plans-convention",
]


class RealRepoTest(unittest.TestCase):
    """The catalog of this repository, which is what users install."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = catalog.load_catalog(REPO)

    def test_counts(self) -> None:
        self.assertEqual(len(self.catalog.skills), 11)
        self.assertEqual(len(self.catalog.commands), 10)
        self.assertEqual(len(self.catalog.agents), 0)

    def test_plans_convention_is_support_and_hidden(self) -> None:
        item = self.catalog.get("skill", "plans-convention")
        self.assertIsNotNone(item)
        self.assertFalse(item.user_invocable)
        self.assertEqual(item.stage, "support")
        self.assertEqual(item.tagline, "")
        self.assertEqual(item.requires, ())
        self.assertIsNone(self.catalog.command_for("plans-convention"))

    def test_make_plan_metadata(self) -> None:
        item = self.catalog.get("skill", "make-plan")
        self.assertIsNotNone(item)
        self.assertTrue(item.user_invocable)
        self.assertEqual(item.stage, "think")
        self.assertEqual(item.tagline, "precise plan.md")
        self.assertTrue(item.description.startswith("Turn a feature"))
        self.assertIn("SKILL.md", item.files)
        self.assertTrue(item.content_hash.startswith("sha256:"))

    def test_every_item_has_a_source_and_hash(self) -> None:
        for item in self.catalog.skills + self.catalog.agents + self.catalog.commands:
            with self.subTest(item=item.key):
                self.assertTrue(item.source.is_absolute())
                self.assertTrue(item.files)
                self.assertTrue(item.content_hash.startswith("sha256:"))
                self.assertEqual(item.files, tuple(sorted(item.files)))

    def test_requires_match_the_plan(self) -> None:
        self.assertEqual({item.name for item in self.catalog.skills}, set(EXPECTED_REQUIRES))
        for item in self.catalog.skills:
            with self.subTest(skill=item.name):
                self.assertEqual(set(item.requires), EXPECTED_REQUIRES[item.name])
                self.assertNotIn(item.name, item.requires)

    def test_required_closure(self) -> None:
        self.assertEqual(
            self.catalog.required_closure({"make-plan"}),
            {"make-plan", "plans-convention", "research-topic"},
        )
        self.assertEqual(self.catalog.required_closure({"plans-convention"}), {"plans-convention"})
        self.assertEqual(self.catalog.required_closure(set()), set())

    def test_dependents_of_plans_convention(self) -> None:
        expected = tuple(sorted(name for name, reqs in EXPECTED_REQUIRES.items() if "plans-convention" in reqs))
        self.assertEqual(self.catalog.dependents("plans-convention"), expected)
        self.assertEqual(self.catalog.dependents("deep-review"), ())

    def test_skill_order_and_stages(self) -> None:
        self.assertEqual([item.name for item in self.catalog.skills], EXPECTED_SKILL_ORDER)
        stages = [item.stage for item in self.catalog.skills]
        self.assertEqual(stages, sorted(stages, key=catalog.STAGE_ORDER.index))

    def test_a_wrapper_per_user_invocable_skill(self) -> None:
        invocable = {item.name for item in self.catalog.skills if item.user_invocable}
        self.assertEqual({item.name for item in self.catalog.commands}, invocable)
        for item in self.catalog.commands:
            with self.subTest(command=item.name):
                self.assertTrue(item.description)
                self.assertFalse(item.requires)

    def test_get_unknown_items(self) -> None:
        self.assertIsNone(self.catalog.get("skill", "nope"))
        self.assertIsNone(self.catalog.get("nope", "make-plan"))
        self.assertIsNone(self.catalog.command_for("nope"))

    def test_key_and_is_dir(self) -> None:
        skill = self.catalog.get("skill", "make-plan")
        command = self.catalog.get("command", "make-plan")
        self.assertEqual(skill.key, "skill/make-plan")
        self.assertTrue(skill.is_dir)
        self.assertEqual(command.key, "command/make-plan")
        self.assertFalse(command.is_dir)


class FindRequiresTest(unittest.TestCase):
    """The prose rules, on crafted texts."""

    def test_placeholder(self) -> None:
        self.assertEqual(
            catalog.find_requires("Run `python3 <x>/scripts/plans.py`.", {"x", "y"}, "self"),
            ("x",),
        )

    def test_load_the_skill_phrase(self) -> None:
        for text in (
            "Load the `x` skill first.",
            "load the `x` skill",
            "LOAD THE `x` SKILL",
            "Load and follow the `x` skill.",
        ):
            with self.subTest(text=text):
                self.assertEqual(catalog.find_requires(text, {"x"}, "self"), ("x",))

    def test_phrase_split_across_a_line_break(self) -> None:
        self.assertEqual(
            catalog.find_requires("(load the\n   `x` skill to find it)", {"x"}, "self"),
            ("x",),
        )

    def test_negative_mentions_do_not_count(self) -> None:
        for text in (
            "Generated by the `x` skill.",
            "This is the `x` skill.",
            "It was written with the `x` skill.",
        ):
            with self.subTest(text=text):
                self.assertEqual(catalog.find_requires(text, {"x"}, "self"), ())

    def test_self_reference_is_ignored(self) -> None:
        text = "Load the `x` skill first; use <x>/scripts/plans.py."
        self.assertEqual(catalog.find_requires(text, {"x", "y"}, "x"), ())

    def test_unknown_names_are_ignored(self) -> None:
        self.assertEqual(catalog.find_requires("Load the `zzz` skill. <zzz>", {"x"}, "self"), ())

    def test_result_is_sorted_and_deduplicated(self) -> None:
        text = "<b> and <a> and load the `c` skill and <a> again, plus <c>."
        self.assertEqual(catalog.find_requires(text, {"c", "b", "a"}, "self"), ("a", "b", "c"))


class ListFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_folder(self) -> Path:
        folder = self.root / "demo"
        (folder / "references").mkdir(parents=True)
        (folder / "SKILL.md").write_text("body", encoding="utf-8")
        (folder / "references" / "guide.md").write_text("guide", encoding="utf-8")
        return folder

    def test_sorted_posix_relative_paths(self) -> None:
        folder = self.make_folder()
        (folder / "z.md").write_text("z", encoding="utf-8")
        (folder / "assets").mkdir()
        (folder / "assets" / "x.png").write_text("png", encoding="utf-8")
        self.assertEqual(
            catalog.list_files(folder),
            ["SKILL.md", "assets/x.png", "references/guide.md", "z.md"],
        )

    def test_file_path_returns_name(self) -> None:
        folder = self.make_folder()
        self.assertEqual(catalog.list_files(folder / "SKILL.md"), ["SKILL.md"])

    def test_ignored_names_and_suffixes(self) -> None:
        folder = self.make_folder()
        cache = folder / "__pycache__"
        cache.mkdir()
        (cache / "script.cpython-39.pyc").write_text("junk", encoding="utf-8")
        (folder / "script.pyc").write_text("junk", encoding="utf-8")
        (folder / "script.pyo").write_text("junk", encoding="utf-8")
        (folder / ".DS_Store").write_text("junk", encoding="utf-8")
        (folder / ".gitkeep").write_text("", encoding="utf-8")
        self.assertEqual(
            catalog.list_files(folder),
            ["SKILL.md", "references/guide.md"],
        )

    def test_missing_path_is_empty(self) -> None:
        self.assertEqual(catalog.list_files(self.root / "nope"), [])

    def test_symlinked_directory_is_not_followed(self) -> None:
        folder = self.make_folder()
        target = self.root / "elsewhere"
        (target / "sub").mkdir(parents=True)
        (target / "sub" / "hidden.md").write_text("hidden", encoding="utf-8")
        try:
            os.symlink(target, folder / "linked", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")
        self.assertNotIn("linked/sub/hidden.md", catalog.list_files(folder))


class ContentHashTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_folder(self) -> Path:
        folder = self.root / "demo"
        (folder / "references").mkdir(parents=True)
        (folder / "SKILL.md").write_text("body", encoding="utf-8")
        (folder / "references" / "guide.md").write_text("guide", encoding="utf-8")
        return folder

    def test_folder_and_copy_have_the_same_hash(self) -> None:
        folder = self.make_folder()
        copy = self.root / "copy"
        shutil.copytree(folder, copy)
        self.assertEqual(len(catalog.list_files(folder)), 2)
        self.assertEqual(catalog.content_hash(folder), catalog.content_hash(copy))

    def test_file_hash(self) -> None:
        folder = self.make_folder()
        self.assertEqual(catalog.content_hash(folder / "SKILL.md"), catalog.content_hash(folder / "SKILL.md"))
        self.assertNotEqual(
            catalog.content_hash(folder / "SKILL.md"),
            catalog.content_hash(folder / "references" / "guide.md"),
        )

    def test_ignored_files_do_not_change_the_hash(self) -> None:
        folder = self.make_folder()
        before = catalog.content_hash(folder)
        cache = folder / "__pycache__"
        cache.mkdir()
        (cache / "plans.cpython-39.pyc").write_text("junk", encoding="utf-8")
        (folder / "plans.pyc").write_text("junk", encoding="utf-8")
        (folder / ".DS_Store").write_text("junk", encoding="utf-8")
        (folder / ".gitkeep").write_text("", encoding="utf-8")
        self.assertEqual(catalog.content_hash(folder), before)

    def test_byte_change_changes_the_hash(self) -> None:
        folder = self.make_folder()
        before = catalog.content_hash(folder)
        (folder / "SKILL.md").write_text("bodz", encoding="utf-8")
        self.assertNotEqual(catalog.content_hash(folder), before)

    def test_file_name_change_changes_the_hash(self) -> None:
        folder = self.make_folder()
        before = catalog.content_hash(folder)
        (folder / "references" / "guide.md").rename(folder / "references" / "other.md")
        self.assertNotEqual(catalog.content_hash(folder), before)


class FixtureCatalogTest(unittest.TestCase):
    """load_catalog on a crafted repository, including agents."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "scripts").mkdir()
        shutil.copy(REPO / "scripts" / "validate.py", self.root / "scripts" / "validate.py")
        (self.root / "scripts" / "draw_workflow.py").write_text(
            "NODES = {'demo': (0, 'main', 'think', 'do the demo', 'core')}\n", encoding="utf-8"
        )
        self.write_skill("demo", "name: demo\ndescription: Do the demo thing.\n", "Load the `base` skill first.\n")
        self.write_skill("base", "name: base\ndescription: Shared rules.\n", "Body.\n")
        (self.root / "agents").mkdir()
        (self.root / "agents" / "helper.md").write_text(
            "---\nname: helper\ndescription: Helps with demos.\n---\n\nPrompt.\n", encoding="utf-8"
        )
        (self.root / "commands").mkdir()
        (self.root / "commands" / "demo.md").write_text(
            "---\ndescription: Do the demo thing.\n---\n\nLoad and follow the `demo` skill.\n",
            encoding="utf-8",
        )
        self.catalog = catalog.load_catalog(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_skill(self, name: str, frontmatter: str, body: str) -> None:
        folder = self.root / "skills" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\n%s---\n\n%s" % (frontmatter, body), encoding="utf-8")

    def test_skills(self) -> None:
        self.assertEqual([item.name for item in self.catalog.skills], ["demo", "base"])
        demo = self.catalog.get("skill", "demo")
        self.assertEqual(demo.description, "Do the demo thing.")
        self.assertTrue(demo.user_invocable)
        self.assertEqual(demo.stage, "think")
        self.assertEqual(demo.tagline, "do the demo")
        self.assertEqual(demo.requires, ("base",))
        self.assertEqual(demo.files, ("SKILL.md",))
        self.assertEqual(demo.source, self.root / "skills" / "demo")
        self.assertEqual(demo.content_hash, catalog.content_hash(self.root / "skills" / "demo"))

        base = self.catalog.get("skill", "base")
        self.assertEqual(base.stage, "support")
        self.assertEqual(base.tagline, "")
        self.assertEqual(base.requires, ())

    def test_agents(self) -> None:
        self.assertEqual([item.name for item in self.catalog.agents], ["helper"])
        agent = self.catalog.agents[0]
        self.assertEqual(agent.description, "Helps with demos.")
        self.assertEqual(agent.source, self.root / "agents" / "helper.md")
        self.assertEqual(agent.files, ("helper.md",))
        self.assertTrue(agent.user_invocable)

    def test_commands(self) -> None:
        self.assertEqual([item.name for item in self.catalog.commands], ["demo"])
        command = self.catalog.command_for("demo")
        self.assertIsNotNone(command)
        self.assertEqual(command.description, "Do the demo thing.")
        self.assertIsNone(self.catalog.command_for("base"))

    def test_required_closure_across_the_fixture(self) -> None:
        self.assertEqual(self.catalog.required_closure({"demo"}), {"demo", "base"})
        self.assertEqual(self.catalog.dependents("base"), ("demo",))


if __name__ == "__main__":
    unittest.main()
