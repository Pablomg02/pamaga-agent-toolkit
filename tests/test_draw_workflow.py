"""Tests for scripts/draw_workflow.py: valid SVG, up to date, every skill drawn."""

from __future__ import annotations

import importlib.util
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "draw_workflow.py"

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("draw_workflow", SCRIPT)
draw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw)


class DrawWorkflowTest(unittest.TestCase):
    def test_svg_is_well_formed(self) -> None:
        for theme in draw.THEMES:
            with self.subTest(theme=theme):
                root = ET.fromstring(draw.svg(theme))
                self.assertTrue(root.tag.endswith("svg"))

    def test_committed_images_are_up_to_date(self) -> None:
        self.assertEqual(draw.main(["--check"]), 0, "run python3 scripts/draw_workflow.py")

    def test_every_user_invocable_skill_is_drawn(self) -> None:
        for skill_md in sorted((REPO / "skills").glob("*/SKILL.md")):
            header = skill_md.read_text(encoding="utf-8").split("---")[1]
            if "user-invocable: false" in header:
                continue
            with self.subTest(skill=skill_md.parent.name):
                self.assertIn(skill_md.parent.name, draw.NODES)

    def test_every_drawn_node_is_a_skill(self) -> None:
        for name in draw.NODES:
            with self.subTest(node=name):
                self.assertTrue((REPO / "skills" / name / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
