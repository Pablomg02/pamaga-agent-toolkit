"""Tests for the installer TUI logo and wordmark.

Only the contracts the screens rely on: the art is well formed, every
renderer respects its width and line limits at every colour depth, and
output is plain ASCII when Unicode is unavailable.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True

from installer.tui import logo  # noqa: E402
from installer.tui import style as tui_style  # noqa: E402

STYLES = (
    tui_style.Style(tui_style.DEPTH_NONE, False),
    tui_style.Style(tui_style.DEPTH_NONE, True),
    tui_style.Style(tui_style.DEPTH_16, True),
    tui_style.Style(tui_style.DEPTH_256, True),
    tui_style.Style(tui_style.DEPTH_TRUECOLOR, True),
    tui_style.Style(tui_style.DEPTH_TRUECOLOR, False),
)


def is_printable_ascii(text: str) -> bool:
    return all(0x20 <= ord(char) < 0x7F for char in text)


class ArtTest(unittest.TestCase):
    """The stored art is rectangular, palette-only and covers the wordmark."""

    def test_macaque_grids(self) -> None:
        allowed = set(logo.PALETTE) | {"."}
        for name, grid in (("open", logo.MACAQUE), ("blink", logo.MACAQUE_BLINK)):
            with self.subTest(grid=name):
                self.assertEqual(len(grid) % 2, 0, "half blocks need an even number of rows")
                self.assertEqual(len({len(row) for row in grid}), 1, "rows must be the same length")
                self.assertLessEqual(set("".join(grid)) - allowed, set(), "unknown pixels")
        self.assertEqual(len(logo.MACAQUE_BLINK), len(logo.MACAQUE))
        self.assertNotEqual(logo.MACAQUE_BLINK, logo.MACAQUE, "a blink must change something")

    def test_font_covers_the_wordmark(self) -> None:
        self.assertEqual(set("".join(logo.WORDMARK)) - set(logo.BLOCK_FONT), set())
        for letter, rows in logo.BLOCK_FONT.items():
            with self.subTest(letter=letter):
                self.assertEqual(len(rows), logo.BLOCK_ROWS)
                self.assertEqual(len({len(row) for row in rows}), 1, "glyph rows must align")


class RenderTest(unittest.TestCase):
    """Renderers stay within their limits at every depth."""

    def test_logo_limits_for_every_style(self) -> None:
        for style in STYLES:
            for blink in (False, True):
                with self.subTest(style=(style.depth, style.unicode), blink=blink):
                    lines = logo.render_logo(style, blink=blink)
                    self.assertLessEqual(len(lines), 16)
                    for line in lines:
                        self.assertLessEqual(tui_style.display_width(line), 32)
                        if not style.unicode or not style.coloured:
                            self.assertTrue(is_printable_ascii(line), line)

    def test_wordmark_limits_for_every_style_and_width(self) -> None:
        for style in STYLES:
            for max_width in (10, 20, 40, 60, 100, 220):
                with self.subTest(style=(style.depth, style.unicode), max_width=max_width):
                    lines = logo.render_wordmark(style, max_width)
                    self.assertTrue(lines)
                    for line in lines:
                        self.assertLessEqual(tui_style.display_width(line), max_width)
                        if not style.unicode:
                            self.assertTrue(is_printable_ascii(tui_style.strip_ansi(line)), line)
                    if not style.coloured:
                        self.assertNotIn("\x1b", "".join(lines))

    def test_module_preview(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = logo.main(["--ascii", "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn(logo.TAGLINE, buffer.getvalue())
        for line in buffer.getvalue().splitlines():
            self.assertTrue(is_printable_ascii(line), repr(line))


if __name__ == "__main__":
    unittest.main()
