"""Tests for the installer TUI logo and wordmark (T6).

The grids are checked as data (shape, palette, blink) and the renderers for
every colour depth: block art and ASCII art must respect their width and line
limits and use printable ASCII when Unicode is unavailable.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
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


def plain(lines):
    return [tui_style.strip_ansi(line) for line in lines]


def is_printable_ascii(text: str) -> bool:
    return all(0x20 <= ord(char) < 0x7F for char in text)


class MacaqueGridTest(unittest.TestCase):
    """The stored pixel art is rectangular, even and palette-only."""

    def test_shape(self) -> None:
        rows = len(logo.MACAQUE)
        self.assertGreaterEqual(rows, 24)
        self.assertLessEqual(rows, 32)
        self.assertEqual(rows % 2, 0, "half blocks need an even number of rows")
        widths = {len(row) for row in logo.MACAQUE}
        self.assertEqual(len(widths), 1, f"rows differ in length: {sorted(widths)}")
        width = widths.pop()
        self.assertGreaterEqual(width, 24)
        self.assertLessEqual(width, 32)

    def test_only_palette_characters(self) -> None:
        allowed = set(logo.PALETTE) | {"."}
        for index, row in enumerate(logo.MACAQUE):
            with self.subTest(row=index):
                self.assertLessEqual(set(row) - allowed, set(), f"row {index} uses unknown pixels")

    def test_palette_is_complete(self) -> None:
        used = set("".join(logo.MACAQUE))
        used.discard(".")
        self.assertEqual(used, set(logo.PALETTE), "every palette colour should be used")
        for key, colour in logo.PALETTE.items():
            with self.subTest(key=key):
                self.assertRegex(colour, r"^#[0-9a-f]{6}$")

    def test_blink_has_the_same_shape(self) -> None:
        self.assertEqual(len(logo.MACAQUE_BLINK), len(logo.MACAQUE))
        for original, blinked in zip(logo.MACAQUE, logo.MACAQUE_BLINK):
            self.assertEqual(len(blinked), len(original))

    def test_blink_differs_only_in_the_eye_area(self) -> None:
        boxes = logo.EYE_BOXES
        differences = 0
        for row, (original, blinked) in enumerate(zip(logo.MACAQUE, logo.MACAQUE_BLINK)):
            for col, (before, after) in enumerate(zip(original, blinked)):
                if before == after:
                    continue
                differences += 1
                in_a_box = any(r0 <= row < r1 and c0 <= col < c1 for r0, r1, c0, c1 in boxes)
                self.assertTrue(in_a_box, f"row {row}, col {col} changed outside the eyes")
        self.assertGreater(differences, 0, "a blink must change something")

    def test_eye_boxes_are_exactly_the_eyes(self) -> None:
        """Each box is one open eye: it holds every `E`/`W` pixel and no other."""
        boxes = logo.EYE_BOXES

        def in_a_box(row: int, col: int) -> bool:
            return any(r0 <= row < r1 and c0 <= col < c1 for r0, r1, c0, c1 in boxes)

        for row, line in enumerate(logo.MACAQUE):
            for col, pixel in enumerate(line):
                with self.subTest(row=row, col=col):
                    if pixel in ("E", "W"):
                        self.assertTrue(in_a_box(row, col), "an eye pixel is outside EYE_BOXES")
                    elif in_a_box(row, col):
                        self.fail(f"non-eye pixel {pixel!r} inside EYE_BOXES")

    def test_blink_closes_every_eye_pixel(self) -> None:
        """Every open eye pixel becomes skin, or the lid line on CLOSED_EYE_ROW."""
        for row, (original, blinked) in enumerate(zip(logo.MACAQUE, logo.MACAQUE_BLINK)):
            for col, (before, after) in enumerate(zip(original, blinked)):
                if before not in ("E", "W"):
                    continue
                expected = "E" if row == logo.CLOSED_EYE_ROW else "S"
                with self.subTest(row=row, col=col):
                    self.assertEqual(after, expected, "a closed eye has no highlight and one dark lid")

    def test_blink_draws_one_lid_line_per_eye(self) -> None:
        """Each eye box keeps exactly one dark line, on CLOSED_EYE_ROW."""
        for row_start, row_end, col_start, col_end in logo.EYE_BOXES:
            rows = [row for row in range(row_start, row_end)
                    if any(logo.MACAQUE_BLINK[row][col] == "E" for col in range(col_start, col_end))]
            with self.subTest(box=(row_start, row_end, col_start, col_end)):
                self.assertEqual(rows, [logo.CLOSED_EYE_ROW], "each closed eye is one lid line")

    def test_blink_keeps_palette_characters(self) -> None:
        allowed = set(logo.PALETTE) | {"."}
        for row in logo.MACAQUE_BLINK:
            self.assertLessEqual(set(row) - allowed, set())


class AsciiMacaqueTest(unittest.TestCase):
    """The hand-drawn fallback respects its size and character set."""

    def test_size(self) -> None:
        self.assertLessEqual(len(logo.MACAQUE_ASCII), 10)
        self.assertLessEqual(max(len(row) for row in logo.MACAQUE_ASCII), 24)
        self.assertGreater(len(logo.MACAQUE_ASCII), 0)

    def test_printable_ascii_only(self) -> None:
        for index, row in enumerate(logo.MACAQUE_ASCII):
            with self.subTest(row=index):
                self.assertTrue(is_printable_ascii(row), f"row {index}: {row!r}")


class RenderLogoTest(unittest.TestCase):
    """`render_logo` at every depth stays within 32 columns and 16 lines."""

    def test_limits_for_every_style(self) -> None:
        for style in STYLES:
            for blink in (False, True):
                with self.subTest(style=(style.depth, style.unicode), blink=blink):
                    lines = logo.render_logo(style, blink=blink)
                    self.assertLessEqual(len(lines), 16)
                    for line in lines:
                        self.assertLessEqual(tui_style.display_width(line), 32)

    def test_no_colour_or_no_unicode_uses_the_ascii_face(self) -> None:
        for style in (tui_style.Style(tui_style.DEPTH_NONE, True),
                      tui_style.Style(tui_style.DEPTH_NONE, False),
                      tui_style.Style(tui_style.DEPTH_TRUECOLOR, False)):
            with self.subTest(style=(style.depth, style.unicode)):
                self.assertEqual(logo.render_logo(style), logo.MACAQUE_ASCII)

    def test_ascii_output_is_printable(self) -> None:
        for style in (tui_style.Style(tui_style.DEPTH_NONE, True), tui_style.Style(tui_style.DEPTH_16, False)):
            with self.subTest(style=style.depth):
                for line in logo.render_logo(style):
                    self.assertTrue(is_printable_ascii(line), line)

    def test_block_art_uses_half_blocks(self) -> None:
        lines = logo.render_logo(tui_style.Style(tui_style.DEPTH_TRUECOLOR, True))
        self.assertEqual(len(lines), len(logo.MACAQUE) // 2)
        for line in plain(lines):
            self.assertLessEqual(set(line) - {" ", "\u2580", "\u2584"}, set())
        for line in lines:
            self.assertTrue(line.endswith("\x1b[0m"), "every line is reset")

    def test_block_art_has_colour_in_truecolor(self) -> None:
        lines = logo.render_logo(tui_style.Style(tui_style.DEPTH_TRUECOLOR, True))
        text = "\n".join(lines)
        for colour in logo.PALETTE.values():
            with self.subTest(colour=colour):
                rgb = tui_style.hex_to_rgb(colour)
                self.assertIn("\x1b[38;2;%d;%d;%d" % rgb, text)

    def test_blink_draws_different_eyes(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_TRUECOLOR, True)
        self.assertNotEqual(logo.render_logo(style, blink=False), logo.render_logo(style, blink=True))
        same = [line for line in logo.render_logo(style, blink=False) if line not in logo.render_logo(style, blink=True)]
        self.assertEqual(len(same), 2, "only the two eye lines change")


class RenderWordmarkTest(unittest.TestCase):
    """`render_wordmark` fits the requested width at every depth."""

    def block_width(self) -> int:
        return max(sum(max(len(row) for row in logo.BLOCK_FONT[letter]) for letter in word) + len(word) - 1
                   for word in logo.WORDMARK)

    def test_limits_for_every_style_and_width(self) -> None:
        block_width = self.block_width()
        for style in STYLES:
            for max_width in (10, 20, block_width - 1, block_width, block_width + 1, 100, 220):
                with self.subTest(style=(style.depth, style.unicode), max_width=max_width):
                    lines = logo.render_wordmark(style, max_width)
                    for line in lines:
                        self.assertLessEqual(tui_style.display_width(line), max_width)

    def test_two_lines_when_it_fits(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_NONE, True)
        self.assertEqual(len(logo.render_wordmark(style, self.block_width())), 10)
        self.assertEqual(len(logo.render_wordmark(style, 220)), 10)

    def test_pamaga_is_centred_over_the_second_line(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_NONE, True)
        lines = logo.render_wordmark(style, 220)
        offset = (self.block_width() - logo._word_width("PAMAGA")) // 2
        self.assertGreater(offset, 0)
        self.assertTrue(lines[0].startswith(" " * offset + "\u2588"), repr(lines[0]))
        # The second word is the widest: no centring offset, only glyph pixels.
        self.assertTrue(lines[5].startswith(" \u2588\u2588"), repr(lines[5]))

    def test_fallback_when_it_does_not_fit(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_TRUECOLOR, True)
        lines = logo.render_wordmark(style, self.block_width() - 1)
        self.assertEqual(len(lines), 1)
        self.assertIn("PAMAGA AGENT TOOLKIT", tui_style.strip_ansi(lines[0]))
        self.assertIn("\x1b[1m", lines[0], "the fallback line is bold")

    def test_fallback_is_truncated_for_narrow_widths(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_NONE, True)
        lines = logo.render_wordmark(style, 10)
        self.assertEqual(len(lines), 1)
        self.assertEqual(tui_style.display_width(lines[0]), 10)

    def test_ascii_mode_uses_hashes(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_NONE, False)
        lines = logo.render_wordmark(style, 220)
        text = "".join(lines)
        self.assertIn("#", text)
        self.assertNotIn("\u2588", text)
        for line in lines:
            self.assertTrue(is_printable_ascii(line), line)

    def test_no_colour_depth_has_no_escapes(self) -> None:
        lines = logo.render_wordmark(tui_style.Style(tui_style.DEPTH_NONE, True), 220)
        self.assertNotIn("\x1b", "".join(lines))

    def test_truecolor_gradient_is_per_column(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_TRUECOLOR, True)
        lines = logo.render_wordmark(style, 220)
        colours = set()
        for match in re.finditer(r"\x1b\[38;2;(\d+;\d+;\d+)m\u2588", "\n".join(lines)):
            colours.add(match.group(1))
        self.assertGreater(len(colours), 20, "a left-to-right gradient should change colour often")

    def test_256_and_16_use_stage_colours_per_letter(self) -> None:
        for depth, pattern in ((tui_style.DEPTH_256, r"\x1b\[38;5;\d+m"),
                               (tui_style.DEPTH_16, r"\x1b\[(3\d|9\d)m")):
            with self.subTest(depth=depth):
                style = tui_style.Style(depth, True)
                text = "".join(logo.render_wordmark(style, 220))
                self.assertRegex(text, pattern)
                self.assertNotIn("38;2;", text)

    def test_narrow_characters_are_not_used(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_TRUECOLOR, True)
        for line in logo.render_wordmark(style, 220):
            for char in tui_style.strip_ansi(line):
                self.assertEqual(tui_style.display_width(char), 1, f"wide character {char!r}")


class PublicApiTest(unittest.TestCase):
    """Tagline, font coverage and the `python3 -m` preview."""

    def test_tagline(self) -> None:
        self.assertEqual(logo.TAGLINE, "Macaco giving macacos instructions")

    def test_font_covers_the_wordmark(self) -> None:
        needed = set("".join(logo.WORDMARK))
        self.assertEqual(needed - set(logo.BLOCK_FONT), set())
        for letter, rows in logo.BLOCK_FONT.items():
            with self.subTest(letter=letter):
                self.assertEqual(len(rows), logo.BLOCK_ROWS)
                self.assertEqual(len({len(row) for row in rows}), 1, "glyph rows must align")
                self.assertLessEqual(max(len(row) for row in rows), 5)
                self.assertTrue(all(set(row) <= {"#", "."} for row in rows))

    def test_module_preview_prints_both_pieces(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = logo.main(["--ascii", "--no-color"])
        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn("#", output)
        self.assertIn(logo.TAGLINE, output)
        for line in output.splitlines():
            self.assertTrue(is_printable_ascii(line), f"no colour and no Unicode means plain ASCII: {line!r}")

    def test_module_runs_with_dash_m(self) -> None:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-m", "installer.tui.logo", "--ascii", "--no-color"],
            cwd=str(SCRIPTS),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(logo.TAGLINE, result.stdout)
        block_rows = [line for line in result.stdout.splitlines() if line and "#" in line and set(line) <= {"#", " "}]
        self.assertGreater(len(block_rows), 5, "the block wordmark should be printed")
        for line in result.stdout.splitlines():
            self.assertTrue(is_printable_ascii(line), repr(line))


if __name__ == "__main__":
    unittest.main()
