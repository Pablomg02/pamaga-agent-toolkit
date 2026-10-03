"""Tests for skills/plans-convention/scripts/plans.py."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
import io
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills" / "plans-convention" / "scripts" / "plans.py"

# Keep __pycache__ out of the skill folders, which get installed as symlinks.
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("plans", SCRIPT)
plans = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plans)


class PlansTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".git").mkdir()
        self.plans_dir = self.root / "plans"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = plans.main(["--plans-dir", str(self.plans_dir), *args])
        return code, out.getvalue().strip(), err.getvalue().strip()

    def new(self, title: str, *extra: str) -> Path:
        code, out, err = self.run_cli("new", "--title", title, *extra)
        self.assertEqual(code, 0, err)
        return Path(out)

    def make_folder(self, status: str, name: str, frontmatter: str | None = None) -> Path:
        folder = self.plans_dir / status / name
        folder.mkdir(parents=True)
        if frontmatter is not None:
            (folder / "plan.md").write_text(frontmatter, encoding="utf-8")
        return folder


class HelpersTest(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(plans.slugify("Add Login"), "add-login")
        self.assertEqual(plans.slugify("Migración a \"v2\" del API!"), "migracion-a-v2-del-api")
        self.assertEqual(plans.slugify("  --Hello__World--  "), "hello-world")
        self.assertEqual(plans.slugify("日本語"), "")

    def test_slugify_truncates_at_word_boundary(self) -> None:
        slug = plans.slugify("word " * 30)
        self.assertLessEqual(len(slug), plans.SLUG_MAX)
        self.assertFalse(slug.endswith("-"))
        self.assertTrue(all(part == "word" for part in slug.split("-")))

    def test_format_and_parse_id(self) -> None:
        self.assertEqual(plans.format_id(7), "0007")
        self.assertEqual(plans.format_id(12345), "12345")
        self.assertEqual(plans.parse_id("0042"), 42)
        with self.assertRaises(plans.PlanError):
            plans.parse_id("abc")

    def test_find_plans_dir_walks_up_to_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            nested = root / "src" / "deep"
            nested.mkdir(parents=True)
            self.assertEqual(plans.find_plans_dir(nested), root.resolve() / "plans")

    def test_read_frontmatter_handles_quotes_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text(
                '---\nid: "0001"\ntitle: "Fix issue #42 with \\"quotes\\""\n'
                "type: plan   # a comment\n---\n# body\n",
                encoding="utf-8",
            )
            meta = plans.read_frontmatter(path)
            self.assertEqual(meta["id"], "0001")
            self.assertEqual(meta["title"], 'Fix issue #42 with "quotes"')
            self.assertEqual(meta["type"], "plan")

    def test_read_frontmatter_unterminated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.md"
            path.write_text("---\nid: 1\n", encoding="utf-8")
            self.assertEqual(plans.read_frontmatter(path), {})


class NewAndIdsTest(PlansTestCase):
    def test_next_id_starts_at_one(self) -> None:
        self.assertEqual(self.run_cli("next-id")[1], "0001")

    def test_new_creates_backlog_folder_from_template(self) -> None:
        folder = self.new("Add login")
        self.assertEqual(folder, self.plans_dir / "backlog" / "0001-add-login")
        text = (folder / "plan.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertIn("# 0001 — Add login", text)
        meta = plans.read_frontmatter(folder / "plan.md")
        self.assertEqual(meta["id"], "0001")
        self.assertEqual(meta["type"], "plan")
        self.assertNotIn("parent", meta)
        for section in ("Justification", "Plan", "Implementation", "Results", "Closure"):
            self.assertIn(f"\n## {section}\n", text)

    def test_every_template_renders(self) -> None:
        for kind in plans.TYPES:
            folder = self.new(f"A {kind}", "--type", kind)
            meta = plans.read_frontmatter(folder / "plan.md")
            self.assertEqual(meta["type"], kind)
            self.assertNotIn("{{", (folder / "plan.md").read_text(encoding="utf-8"))

    def test_title_with_quotes_round_trips(self) -> None:
        folder = self.new('Support "smart" quotes #2')
        meta = plans.read_frontmatter(folder / "plan.md")
        self.assertEqual(meta["title"], 'Support "smart" quotes #2')

    def test_ids_are_never_reused(self) -> None:
        self.new("One")
        second = self.new("Two")
        self.run_cli("move", "1", "done")
        self.assertEqual(self.run_cli("next-id")[1], "0003")
        self.assertTrue(second.name.startswith("0002-"))

    def test_next_id_uses_max_not_gaps(self) -> None:
        self.make_folder("done", "0005-old", '---\nid: "0005"\ntitle: Old\ntype: plan\n---\n')
        self.assertEqual(self.run_cli("next-id")[1], "0006")

    def test_check_id(self) -> None:
        self.new("One")
        code, out, _ = self.run_cli("check-id", "1")
        self.assertEqual(code, 1)
        self.assertIn("used:", out)
        code, out, _ = self.run_cli("check-id", "0002")
        self.assertEqual(code, 0)
        self.assertEqual(out, "free: 0002")

    def test_explicit_slug_is_validated(self) -> None:
        code, _, err = self.run_cli("new", "--title", "X", "--slug", "Bad Slug")
        self.assertEqual(code, 1)
        self.assertIn("invalid slug", err)

    def test_title_without_ascii_needs_slug(self) -> None:
        code, _, err = self.run_cli("new", "--title", "日本語")
        self.assertEqual(code, 1)
        self.assertIn("invalid slug", err)
        self.assertEqual(self.new("日本語", "--slug", "japanese").name, "0001-japanese")

    def test_parent_must_be_a_roadmap(self) -> None:
        self.new("Roadmap", "--type", "roadmap")
        self.new("Ticket", "--type", "ticket")
        child = self.new("Child", "--parent", "1")
        self.assertEqual(plans.read_frontmatter(child / "plan.md")["parent"], "0001")
        code, _, err = self.run_cli("new", "--title", "Bad", "--parent", "2")
        self.assertEqual(code, 1)
        self.assertIn("not a roadmap", err)
        code, _, err = self.run_cli("new", "--title", "Bad", "--parent", "99")
        self.assertEqual(code, 1)
        self.assertIn("no plan with id 0099", err)


class FindMoveListTest(PlansTestCase):
    def test_find_by_id_and_path(self) -> None:
        folder = self.new("Add login")
        self.assertEqual(self.run_cli("find", "1")[1], str(folder))
        self.assertEqual(self.run_cli("find", str(folder))[1], str(folder))
        code, _, err = self.run_cli("find", "7")
        self.assertEqual(code, 1)
        self.assertIn("no plan with id 0007", err)

    def test_find_rejects_non_plan_directory(self) -> None:
        code, _, err = self.run_cli("find", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("is not a plan folder", err)

    def test_move_between_statuses(self) -> None:
        self.new("Add login")
        code, out, _ = self.run_cli("move", "1", "in-progress")
        self.assertEqual(code, 0)
        self.assertEqual(Path(out), self.plans_dir / "in-progress" / "0001-add-login")
        self.assertTrue((Path(out) / "plan.md").is_file())
        self.assertFalse((self.plans_dir / "backlog" / "0001-add-login").exists())
        # moving to the same status is a no-op
        self.assertEqual(self.run_cli("move", "1", "in-progress")[0], 0)

    def test_move_refuses_duplicated_id(self) -> None:
        self.make_folder("backlog", "0001-a", '---\nid: "0001"\ntitle: A\ntype: plan\n---\n')
        self.make_folder("done", "0001-b", '---\nid: "0001"\ntitle: B\ntype: plan\n---\n')
        code, _, err = self.run_cli("move", "1", "in-progress")
        self.assertEqual(code, 1)
        self.assertIn("duplicated", err)

    def test_list_filters(self) -> None:
        self.new("Roadmap", "--type", "roadmap")
        self.new("Child", "--parent", "1")
        self.run_cli("move", "2", "in-progress")
        out = self.run_cli("list")[1]
        self.assertIn("0001  backlog      roadmap  Roadmap", out)
        self.assertIn("0002  in-progress  plan     Child (parent 0001)", out)
        ids = lambda *args: [line.split()[0] for line in self.run_cli("list", *args)[1].splitlines()]
        self.assertEqual(ids("--status", "in-progress"), ["0002"])
        self.assertEqual(ids("--type", "roadmap"), ["0001"])
        self.assertEqual(self.run_cli("list", "--status", "done")[1], "no plans found")


class ValidateTest(PlansTestCase):
    def test_no_plans_folder_is_fine(self) -> None:
        code, out, _ = self.run_cli("validate")
        self.assertEqual(code, 0)
        self.assertIn("no plans folder", out)

    def test_valid_tree(self) -> None:
        self.new("Roadmap", "--type", "roadmap")
        self.new("Child", "--parent", "1")
        code, out, _ = self.run_cli("validate")
        self.assertEqual(code, 0, out)
        self.assertIn("ok: 2 plan folder(s)", out)

    def test_detects_problems(self) -> None:
        self.make_folder("backlog", "0001-a", '---\nid: "0001"\ntitle: A\ntype: plan\n---\n')
        self.make_folder("done", "0001-b", '---\nid: "0001"\ntitle: B\ntype: plan\n---\n')
        self.make_folder("backlog", "0002-no-plan")
        self.make_folder("backlog", "0003-wrong-id", '---\nid: "0004"\ntitle: W\ntype: plan\n---\n')
        self.make_folder("backlog", "0005-bad-type", '---\nid: "0005"\ntitle: T\ntype: epic\n---\n')
        self.make_folder("backlog", "0006-orphan", '---\nid: "0006"\ntitle: O\ntype: plan\nparent: "0099"\n---\n')
        self.make_folder("backlog", "0007-no-fm", "# no frontmatter\n")
        self.make_folder("backlog", "Bad_Name")
        (self.plans_dir / "notes.txt").write_text("x", encoding="utf-8")
        (self.plans_dir / "backlog" / "stray.md").write_text("x", encoding="utf-8")

        code, out, _ = self.run_cli("validate")
        self.assertEqual(code, 1)
        for expected in (
            "id 0001 is used by several folders",
            "0002-no-plan: missing plan.md",
            "frontmatter id '0004' != folder id '0003'",
            "type must be one of",
            "parent 0099 does not exist",
            "missing or unterminated frontmatter",
            "Bad_Name: folder name must be",
            "notes.txt: only backlog",
            "stray.md: unexpected file",
        ):
            self.assertIn(expected, out)

    def test_parent_that_is_not_roadmap(self) -> None:
        self.new("Plan")
        self.make_folder("backlog", "0002-child", '---\nid: "0002"\ntitle: C\ntype: plan\nparent: "0001"\n---\n')
        code, out, _ = self.run_cli("validate")
        self.assertEqual(code, 1)
        self.assertIn("parent 0001 is not a roadmap", out)


class PageTest(PlansTestCase):
    PAGE = (
        "<!doctype html>\n<html><head>\n<title>t</title>\n<style>body{}</style>\n</head>"
        "<body><p>hi</p></body></html>\n"
    )

    def test_page_lifecycle(self) -> None:
        folder = self.new("Add login")
        self.assertEqual(self.run_cli("page-status", "1")[1], "missing")
        code, _, err = self.run_cli("stamp-page", "1")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)

        (folder / "plan.html").write_text(self.PAGE, encoding="utf-8")
        self.assertEqual(self.run_cli("page-status", "1")[1], "stale")  # never stamped

        code, out, _ = self.run_cli("stamp-page", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_cli("page-status", "1")[1], "fresh")
        self.assertEqual(self.run_cli("validate")[0], 0)

        # stamping again replaces the hash instead of adding a second meta
        self.run_cli("stamp-page", "1")
        self.assertEqual((folder / "plan.html").read_text().count("plan-source-sha256"), 1)

        with (folder / "plan.md").open("a", encoding="utf-8") as handle:
            handle.write("\nA change.\n")
        self.assertEqual(self.run_cli("page-status", "1")[1], "stale")
        code, out, _ = self.run_cli("validate")
        self.assertEqual(code, 0)
        self.assertIn("warning:", out)
        self.assertIn("out of date", out)

    def test_page_status_survives_moves(self) -> None:
        folder = self.new("Add login")
        (folder / "plan.html").write_text(self.PAGE, encoding="utf-8")
        self.run_cli("stamp-page", "1")
        self.run_cli("move", "1", "done")
        self.assertEqual(self.run_cli("page-status", "1")[1], "fresh")

    def test_stamp_reports_external_resources(self) -> None:
        folder = self.new("Add login")
        cases = [
            '<script src="https://cdn.example.com/x.js"></script>',
            '<link rel="stylesheet" href="https://fonts.example.com/f.css">',
            '<img src="diagram.png">',
            "<style>@import url(https://x.example/y.css);</style>",
            "<div style=\"background: url('bg.png')\"></div>",
            '<iframe srcdoc="x"></iframe>',
        ]
        for snippet in cases:
            with self.subTest(snippet=snippet):
                html = self.PAGE.replace("<p>hi</p>", snippet)
                (folder / "plan.html").write_text(html, encoding="utf-8")
                code, out, _ = self.run_cli("stamp-page", "1")
                self.assertEqual(code, 1, out)
                self.assertIn("not self-contained", out)

    def test_stamp_accepts_inline_resources(self) -> None:
        folder = self.new("Add login")
        html = self.PAGE.replace(
            "<p>hi</p>",
            '<img src="data:image/png;base64,AAAA"><a href="https://example.com">link</a>'
            '<a href="#why">why</a><script>var a = 1;</script>',
        )
        (folder / "plan.html").write_text(html, encoding="utf-8")
        code, out, _ = self.run_cli("stamp-page", "1")
        self.assertEqual(code, 0, out)

    def test_bundled_template_is_self_contained(self) -> None:
        folder = self.new("Add login")
        template = REPO / "skills" / "plan-page" / "assets" / "template.html"
        (folder / "plan.html").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        code, out, _ = self.run_cli("stamp-page", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_cli("page-status", "1")[1], "fresh")


class DefaultPlansDirTest(unittest.TestCase):
    def test_script_finds_plans_from_a_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "src").mkdir()
            previous = os.getcwd()
            os.chdir(root / "src")
            try:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(plans.main(["new", "--title", "Hello"]), 0)
            finally:
                os.chdir(previous)
            self.assertTrue((root / "plans" / "backlog" / "0001-hello" / "plan.md").is_file())


if __name__ == "__main__":
    unittest.main()
