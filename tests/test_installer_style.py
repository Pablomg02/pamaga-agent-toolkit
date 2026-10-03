"""Tests for the installer TUI primitives: style, widgets and terminal (T5).

Key decoding, colour depth, text measurement and every widget are pure and
tested directly; `Terminal` is exercised through a pty so raw mode, the
alternate screen, key reads and restoration are checked without the real
standard input.
"""

from __future__ import annotations

import importlib.util
import io
import os
import re
import signal
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True

from installer.tui import style as tui_style  # noqa: E402
from installer.tui import terminal as tui_terminal  # noqa: E402
from installer.tui import widgets as tui_widgets  # noqa: E402

spec = importlib.util.spec_from_file_location("draw_workflow", SCRIPTS / "draw_workflow.py")
draw_workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw_workflow)


class DecodeTest(unittest.TestCase):
    """`decode(bytes) -> list[str]`, the pure key decoder used by read_key."""

    def test_csi_arrows(self) -> None:
        for final, name in ((b"A", "up"), (b"B", "down"), (b"C", "right"), (b"D", "left")):
            with self.subTest(sequence=final):
                self.assertEqual(tui_terminal.decode(b"\x1b[" + final), [name])

    def test_vt100_arrows(self) -> None:
        for final, name in ((b"A", "up"), (b"B", "down"), (b"C", "right"), (b"D", "left")):
            with self.subTest(sequence=final):
                self.assertEqual(tui_terminal.decode(b"\x1bO" + final), [name])

    def test_paging(self) -> None:
        self.assertEqual(tui_terminal.decode(b"\x1b[5~"), ["pgup"])
        self.assertEqual(tui_terminal.decode(b"\x1b[6~"), ["pgdn"])

    def test_home_and_end(self) -> None:
        self.assertEqual(tui_terminal.decode(b"\x1b[H"), ["home"])
        self.assertEqual(tui_terminal.decode(b"\x1b[F"), ["end"])
        self.assertEqual(tui_terminal.decode(b"\x1b[1~"), ["home"])
        self.assertEqual(tui_terminal.decode(b"\x1b[4~"), ["end"])
        self.assertEqual(tui_terminal.decode(b"\x1bOH"), ["home"])
        self.assertEqual(tui_terminal.decode(b"\x1bOF"), ["end"])

    def test_enter(self) -> None:
        self.assertEqual(tui_terminal.decode(b"\r"), ["enter"])
        self.assertEqual(tui_terminal.decode(b"\n"), ["enter"])
        self.assertEqual(tui_terminal.decode(b"\r\n"), ["enter"], "CRLF is one Enter")

    def test_backspace(self) -> None:
        self.assertEqual(tui_terminal.decode(b"\x7f"), ["backspace"])
        self.assertEqual(tui_terminal.decode(b"\x08"), ["backspace"])

    def test_other_named_keys(self) -> None:
        self.assertEqual(tui_terminal.decode(b"\x03"), ["ctrl-c"])
        self.assertEqual(tui_terminal.decode(b"\t"), ["tab"])
        self.assertEqual(tui_terminal.decode(b" "), ["space"])
        self.assertEqual(tui_terminal.decode(b"\x1b"), ["esc"])
        self.assertEqual(tui_terminal.decode(b"\x1b[3~"), ["delete"])

    def test_printable_characters(self) -> None:
        self.assertEqual(tui_terminal.decode(b"a"), ["a"])
        self.assertEqual(tui_terminal.decode(b"/"), ["/"])
        self.assertEqual(tui_terminal.decode(b"\xc3\xa9"), ["\u00e9"], "UTF-8 input")

    def test_two_keys_in_one_read(self) -> None:
        self.assertEqual(tui_terminal.decode(b"ab"), ["a", "b"])
        self.assertEqual(tui_terminal.decode(b"\x1b[A\x1b[B"), ["up", "down"])
        self.assertEqual(tui_terminal.decode(b"\x7f\x03"), ["backspace", "ctrl-c"])
        self.assertEqual(tui_terminal.decode(b"\x1b[5~\r"), ["pgup", "enter"])

    def test_every_sequence_is_a_known_name(self) -> None:
        sequences = [b"\x1b[A", b"\x1b[B", b"\x1b[C", b"\x1b[D", b"\x1bOA", b"\x1bOB", b"\x1bOC", b"\x1bOD",
                     b"\x1b[5~", b"\x1b[6~", b"\x1b[H", b"\x1b[F", b"\x1b[1~", b"\x1b[4~"]
        for sequence in sequences:
            with self.subTest(sequence=sequence):
                keys = tui_terminal.decode(sequence)
                self.assertEqual(len(keys), 1)
                self.assertIn(keys[0], tui_terminal.KEY_NAMES)

    def test_unknown_control_bytes_are_ignored(self) -> None:
        self.assertEqual(tui_terminal.decode(b"\x01\x02"), [])

    def test_windows_decoding(self) -> None:
        for chars, name in (("\x00H", "up"), ("\xe0P", "down"), ("\x00K", "left"), ("\x00M", "right"),
                            ("\x00I", "pgup"), ("\x00Q", "pgdn"), ("\x00G", "home"), ("\x00O", "end")):
            with self.subTest(chars=chars):
                self.assertEqual(tui_terminal.decode_windows(chars), [name])
        self.assertEqual(tui_terminal.decode_windows("\r"), ["enter"])
        self.assertEqual(tui_terminal.decode_windows("\x1b"), ["esc"])
        self.assertEqual(tui_terminal.decode_windows("\t"), ["tab"])
        self.assertEqual(tui_terminal.decode_windows("\x08"), ["backspace"])
        self.assertEqual(tui_terminal.decode_windows(" "), ["space"])
        self.assertEqual(tui_terminal.decode_windows("\x03"), ["ctrl-c"])
        self.assertEqual(tui_terminal.decode_windows("a\x00M"), ["a", "right"])


class DepthTest(unittest.TestCase):
    """Colour depth detection from an environment mapping."""

    def test_environment_matrix(self) -> None:
        cases = (
            ({"TERM": "xterm-256color", "COLORTERM": "truecolor"}, tui_style.DEPTH_TRUECOLOR),
            ({"TERM": "xterm-256color", "COLORTERM": "24bit"}, tui_style.DEPTH_TRUECOLOR),
            ({"TERM": "xterm-256color"}, tui_style.DEPTH_256),
            ({"TERM": "screen-256color"}, tui_style.DEPTH_256),
            ({"TERM": "xterm"}, tui_style.DEPTH_16),
            ({}, tui_style.DEPTH_16),
            ({"TERM": "xterm", "NO_COLOR": "1"}, tui_style.DEPTH_NONE),
            ({"TERM": "xterm", "NO_COLOR": "1", "COLORTERM": "truecolor"}, tui_style.DEPTH_NONE),
            ({"TERM": "xterm", "NO_COLOR": ""}, tui_style.DEPTH_16),
            ({"TERM": "dumb"}, tui_style.DEPTH_NONE),
            ({"TERM": "dumb", "COLORTERM": "truecolor"}, tui_style.DEPTH_NONE),
        )
        for env, expected in cases:
            with self.subTest(env=env):
                self.assertEqual(tui_style.detect_depth(env), expected)

    def test_no_color_flag_wins(self) -> None:
        self.assertEqual(tui_style.detect_depth({"TERM": "xterm-256color"}, no_color=True),
                         tui_style.DEPTH_NONE)

    def test_style_constructor_and_flags(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_16, True)
        self.assertEqual(style.depth, tui_style.DEPTH_16)
        self.assertTrue(style.unicode)
        self.assertTrue(style.coloured)
        self.assertFalse(tui_style.Style(tui_style.DEPTH_NONE, False).coloured)
        with self.assertRaises(ValueError):
            tui_style.Style("sepia")

    def test_style_detect(self) -> None:
        self.assertEqual(tui_style.Style.detect(env={"TERM": "xterm"}, encoding="utf-8").depth, tui_style.DEPTH_16)
        self.assertTrue(tui_style.Style.detect(env={"TERM": "xterm"}, encoding="UTF-8").unicode)
        self.assertFalse(tui_style.Style.detect(env={"TERM": "xterm"}, encoding="ascii").unicode)
        self.assertFalse(tui_style.Style.detect(env={"TERM": "xterm"}, ascii=True, encoding="utf-8").unicode)
        self.assertEqual(tui_style.Style.detect(env={"TERM": "dumb"}, encoding="utf-8").depth,
                         tui_style.DEPTH_NONE)

    def test_theme_matches_the_readme_diagram(self) -> None:
        self.assertEqual(tui_style.THEME, dict(draw_workflow.THEMES["dark"]))

    def test_stage_colour_falls_back_to_muted(self) -> None:
        self.assertEqual(tui_style.stage_colour("think"), tui_style.THEME["think"])
        self.assertEqual(tui_style.stage_colour("support"), tui_style.THEME["muted"])
        self.assertEqual(tui_style.stage_colour("nonsense"), tui_style.THEME["muted"])


class ColourTest(unittest.TestCase):
    """`fg`/`bg` at every depth, including the no-colour contract."""

    def test_fg_none_returns_text_unchanged(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_NONE, True)
        self.assertEqual(style.fg("hello", "#58a6ff"), "hello")
        self.assertEqual(style.bg("hello", "#58a6ff"), "hello")
        self.assertEqual(style.bold("hello"), "hello")
        self.assertEqual(style.dim("hello"), "hello")
        self.assertEqual(style.italic("hello"), "hello")
        self.assertEqual(style.reverse("hello"), "hello")

    def test_fg_truecolor(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_TRUECOLOR, True)
        self.assertEqual(style.fg("x", "#58a6ff"), "\x1b[38;2;88;166;255mx\x1b[39m")
        self.assertEqual(style.bg("x", "#0d1117"), "\x1b[48;2;13;17;23mx\x1b[49m")

    def test_fg_256_uses_the_palette(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_256, True)
        match = re.fullmatch(r"\x1b\[38;5;(\d+)mx\x1b\[39m", style.fg("x", "#58a6ff"))
        self.assertIsNotNone(match)
        self.assertLess(int(match.group(1)), 256)
        self.assertTrue(re.fullmatch(r"\x1b\[48;5;\d+mx\x1b\[49m", style.bg("x", "#58a6ff")))

    def test_fg_16_uses_basic_colours(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_16, True)
        self.assertTrue(re.fullmatch(r"\x1b\[(3\d|9\d)mx\x1b\[39m", style.fg("x", "#58a6ff")))
        self.assertTrue(re.fullmatch(r"\x1b\[(4\d|10\d)mx\x1b\[49m", style.bg("x", "#58a6ff")))

    def test_attributes(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_TRUECOLOR, True)
        self.assertEqual(style.bold("x"), "\x1b[1mx\x1b[22m")
        self.assertEqual(style.dim("x"), "\x1b[2mx\x1b[22m")
        self.assertEqual(style.italic("x"), "\x1b[3mx\x1b[23m")
        self.assertEqual(style.reverse("x"), "\x1b[7mx\x1b[27m")

    def test_hex_helpers(self) -> None:
        self.assertEqual(tui_style.hex_to_rgb("#58a6ff"), (88, 166, 255))
        self.assertEqual(tui_style.hex_to_rgb("#fff"), (255, 255, 255))
        self.assertEqual(tui_style.rgb_to_hex((88, 166, 255)), "#58a6ff")
        self.assertEqual(tui_style.hex_to_rgb(tui_style.rgb_to_hex((300, -5, 128))), (255, 0, 128))
        with self.assertRaises(ValueError):
            tui_style.hex_to_rgb("not-a-colour")


class GlyphTest(unittest.TestCase):
    """Glyph names and their ASCII fallbacks."""

    def test_box_glyphs(self) -> None:
        self.assertEqual(tui_style.glyph("top_left"), "\u256d")
        self.assertEqual(tui_style.glyph("top_right"), "\u256e")
        self.assertEqual(tui_style.glyph("bottom_left"), "\u2570")
        self.assertEqual(tui_style.glyph("bottom_right"), "\u256f")
        self.assertEqual(tui_style.glyph("hline"), "\u2500")
        self.assertEqual(tui_style.glyph("vline"), "\u2502")
        self.assertEqual(tui_style.glyph("top_left", unicode=False), "+")
        self.assertEqual(tui_style.glyph("hline", unicode=False), "-")
        self.assertEqual(tui_style.glyph("vline", unicode=False), "|")

    def test_status_glyphs(self) -> None:
        expected = {
            "linked": ("\u21c4", "="),
            "up_to_date": ("\u25cf", "*"),
            "outdated": ("\u2191", "^"),
            "modified": ("\u270e", "~"),
            "unmanaged": ("!", "!"),
            "foreign_link": ("!", "!"),
            "orphaned": ("\u2717", "x"),
            "not_installed": ("\u25cb", "."),
        }
        for name, (unicode_glyph, ascii_glyph) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(tui_style.glyph(name), unicode_glyph)
                self.assertEqual(tui_style.glyph(name, unicode=False), ascii_glyph)
                self.assertEqual(tui_style.glyph(name.replace("_", "-")), unicode_glyph, "state.Status values")

    def test_other_glyphs(self) -> None:
        self.assertEqual(tui_style.glyph("arrow"), "\u25b8")
        self.assertEqual(tui_style.glyph("arrow", unicode=False), ">")
        self.assertEqual(tui_style.glyph("checkbox_on"), "\u25c9")
        self.assertEqual(tui_style.glyph("checkbox_on", unicode=False), "[x]")
        self.assertEqual(tui_style.glyph("checkbox_off", unicode=False), "[ ]")
        self.assertEqual(tui_style.glyph("bar_full", unicode=False), "#")
        self.assertEqual(tui_style.glyph("bar_empty", unicode=False), "-")

    def test_unicode_glyphs_are_one_cell_wide(self) -> None:
        for name, char in tui_style.UNICODE_GLYPHS.items():
            with self.subTest(name=name):
                self.assertEqual(tui_style.display_width(char), 1, f"{name} = {char!r}")

    def test_unknown_glyph_raises(self) -> None:
        with self.assertRaises(KeyError):
            tui_style.glyph("banana")

    def test_style_glyph_respects_unicode(self) -> None:
        self.assertEqual(tui_style.Style(tui_style.DEPTH_16, True).glyph("arrow"), "\u25b8")
        self.assertEqual(tui_style.Style(tui_style.DEPTH_16, False).glyph("arrow"), ">")


class WidthTest(unittest.TestCase):
    """`display_width` and `strip_ansi`."""

    def test_plain_text(self) -> None:
        self.assertEqual(tui_style.display_width(""), 0)
        self.assertEqual(tui_style.display_width("hello"), 5)

    def test_ansi_is_zero_width(self) -> None:
        self.assertEqual(tui_style.display_width("\x1b[31mred\x1b[0m"), 3)
        self.assertEqual(tui_style.display_width("\x1b[38;2;1;2;3mx\x1b[39m\x1b[K"), 1)
        self.assertEqual(tui_style.strip_ansi("\x1b[1mbold\x1b[22m"), "bold")

    def test_cjk_is_two_cells(self) -> None:
        self.assertEqual(tui_style.display_width("\u65e5\u672c"), 4)
        self.assertEqual(tui_style.display_width("\uff21"), 2, "fullwidth A")

    def test_combining_marks_are_zero_width(self) -> None:
        self.assertEqual(tui_style.display_width("e\u0301"), 1)

    def test_ansi_codes_do_not_raise_inside_measurement(self) -> None:
        self.assertEqual(tui_style.display_width("\x1b[38;2;88;166;255m\u65e5\x1b[39m"), 2)


class TruncateTest(unittest.TestCase):
    """`truncate` never exceeds the width and closes open styles."""

    SAMPLES = (
        "hello world",
        "\x1b[31mhello world\x1b[0m",
        "\u65e5\u672c\u8a9e\u3067\u3059",
        "\x1b[1m\u65e5\u672c\u8a9e\x1b[22m",
        "\u25b8 \u25c9 make-plan \u2191",
        "",
    )

    def test_short_text_is_untouched(self) -> None:
        self.assertEqual(tui_style.truncate("hello", 10), "hello")
        self.assertEqual(tui_style.truncate("\x1b[31mhello\x1b[0m", 5), "\x1b[31mhello\x1b[0m")

    def test_never_exceeds_the_width(self) -> None:
        for text in self.SAMPLES:
            for width in range(0, 14):
                with self.subTest(text=text, width=width):
                    self.assertLessEqual(tui_style.display_width(tui_style.truncate(text, width)), width)

    def test_adds_the_ellipsis(self) -> None:
        self.assertEqual(tui_style.truncate("hello world", 6), "hello\u2026")
        self.assertEqual(tui_style.truncate("hello", 1), "\u2026")
        self.assertEqual(tui_style.truncate("hello", 0), "")
        self.assertEqual(tui_style.truncate("hello", 3, ellipsis="..."), "...")

    def test_closes_open_styles(self) -> None:
        cut = tui_style.truncate("\x1b[31mhello world\x1b[0m", 8)
        self.assertEqual(tui_style.display_width(cut), 8)
        self.assertTrue(cut.endswith("\x1b[0m"))
        plain = tui_style.truncate("hello world", 8)
        self.assertNotIn("\x1b[0m", plain, "no styles, no reset")

    def test_wide_characters_are_not_split(self) -> None:
        self.assertEqual(tui_style.truncate("\u65e5\u672c\u8a9e", 4), "\u65e5\u2026")
        self.assertEqual(tui_style.truncate("\u65e5\u672c\u8a9e", 2), "\u2026")
        for width in (2, 3, 4, 5):
            with self.subTest(width=width):
                cut = tui_style.truncate("\u65e5\u672c\u8a9e", width)
                self.assertLessEqual(tui_style.display_width(cut), width)

    def test_style_truncate_uses_ascii_ellipsis(self) -> None:
        ascii_style = tui_style.Style(tui_style.DEPTH_NONE, False)
        self.assertEqual(ascii_style.truncate("hello world", 6), "hel...")
        self.assertEqual(ascii_style.truncate("hello world", 2), "..")

    def test_fit_is_exactly_the_width(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_16, True)
        self.assertEqual(tui_style.display_width(style.fit("hi", 5)), 5)
        self.assertEqual(tui_style.display_width(style.fit("\u65e5\u672c\u8a9e", 4)), 4)
        self.assertEqual(style.fit("hi", 5), "hi   ")


class PadTest(unittest.TestCase):
    """`pad` pads to a width and leaves wider text alone."""

    def test_pads_to_width(self) -> None:
        self.assertEqual(tui_style.pad("ab", 5), "ab   ")
        self.assertEqual(tui_style.pad("", 3), "   ")
        self.assertEqual(tui_style.pad("\x1b[31mab\x1b[0m", 4), "\x1b[31mab\x1b[0m  ")

    def test_keeps_wider_text(self) -> None:
        self.assertEqual(tui_style.pad("abcd", 2), "abcd")
        self.assertEqual(tui_style.pad("\u65e5\u672c", 3), "\u65e5\u672c")

    def test_wide_characters(self) -> None:
        self.assertEqual(tui_style.display_width(tui_style.pad("\u65e5", 5)), 5)


class WrapTest(unittest.TestCase):
    """`wrap` folds text to the width, including CJK and styled text."""

    def test_wraps_at_word_boundaries(self) -> None:
        self.assertEqual(tui_style.wrap("one two three", 7), ["one two", "three"])
        self.assertEqual(tui_style.wrap("one two", 7), ["one two"])

    def test_hard_splits_long_words(self) -> None:
        self.assertEqual(tui_style.wrap("one twothree", 3), ["one", "two", "thr", "ee"])

    def test_cjk(self) -> None:
        self.assertEqual(tui_style.wrap("\u65e5\u672c\u8a9e\u3067\u3059", 4),
                         ["\u65e5\u672c", "\u8a9e\u3067", "\u3059"])

    def test_newlines_start_new_lines(self) -> None:
        self.assertEqual(tui_style.wrap("a\n\nb", 5), ["a", "", "b"])

    def test_ansi_is_measured_invisibly(self) -> None:
        lines = tui_style.wrap("\x1b[1mhello\x1b[0m world", 5)
        self.assertEqual(lines, ["\x1b[1mhello\x1b[0m", "world"])
        for line in lines:
            self.assertLessEqual(tui_style.display_width(line), 5)

    def test_never_exceeds_the_width(self) -> None:
        text = "the quick brown fox \u65e5\u672c\u8a9e jumps over the lazy dog"
        for width in range(2, 12):
            with self.subTest(width=width):
                for line in tui_style.wrap(text, width):
                    self.assertLessEqual(tui_style.display_width(line), width)

    def test_a_lone_wide_character_exceeds_a_width_of_one(self) -> None:
        # A double-width character cannot be cut in half, so width 1 keeps it.
        for line in tui_style.wrap("ascii only", 1):
            self.assertEqual(tui_style.display_width(line), 1)
        self.assertEqual(tui_style.wrap("\u65e5", 1), ["\u65e5"])

    def test_zero_width(self) -> None:
        self.assertEqual(tui_style.wrap("hello", 0), [])


class WidgetsTest(unittest.TestCase):
    """Every widget renders exactly the requested width."""

    def setUp(self) -> None:
        self.unicode = tui_style.Style(tui_style.DEPTH_NONE, True)
        self.ascii = tui_style.Style(tui_style.DEPTH_NONE, False)

    def test_box_width(self) -> None:
        for width in (4, 8, 20, 30, 61):
            with self.subTest(width=width):
                lines = tui_widgets.box("Skills", ["make-plan", "an excessively long line " * 3],
                                        width, tui_style.THEME["think"], self.unicode)
                self.assertEqual(len(lines), 4)
                for line in lines:
                    self.assertEqual(tui_style.display_width(line), width)

    def test_box_tiny_widths(self) -> None:
        for width in (1, 2, 3):
            with self.subTest(width=width):
                lines = tui_widgets.box("Skills", ["content"], width, tui_style.THEME["think"], self.unicode)
                for line in lines:
                    self.assertEqual(tui_style.display_width(line), width)
        self.assertEqual(tui_widgets.box("x", [], 0, "#ffffff", self.unicode), [])

    def test_box_borders_and_title(self) -> None:
        lines = tui_widgets.box("Skills", ["body"], 22, tui_style.THEME["think"], self.unicode)
        self.assertTrue(lines[0].startswith("\u256d Skills \u2500"))
        self.assertTrue(lines[0].endswith("\u256e"))
        self.assertTrue(lines[1].startswith("\u2502 body"))
        self.assertTrue(lines[-1].startswith("\u2570"))
        self.assertTrue(lines[-1].endswith("\u256f"))

    def test_box_ascii_fallback(self) -> None:
        lines = tui_widgets.box("Skills", ["body"], 20, tui_style.THEME["think"], self.ascii)
        self.assertTrue(lines[0].startswith("+ Skills -"))
        for line in lines:
            self.assertTrue(line.isascii(), line)

    def test_box_colours_content_is_not_disturbed(self) -> None:
        styled = self.unicode.fg("modificado", tui_style.THEME["keep"])
        lines = tui_widgets.box("t", [styled], 14, tui_style.THEME["think"], self.unicode)
        self.assertIn("modificado", tui_style.strip_ansi(lines[1]))
        self.assertEqual(tui_style.display_width(lines[1]), 14)

    def test_progress_bar_width_and_fill(self) -> None:
        bar = tui_widgets.progress_bar(3, 10, 20, self.unicode)
        self.assertEqual(tui_style.display_width(bar), 20)
        self.assertIn("\u2501", bar)
        self.assertIn("\u2500", bar)
        full = tui_widgets.progress_bar(9, 9, 10, self.unicode)
        self.assertEqual(tui_style.strip_ansi(full), "\u2501" * 10)
        empty = tui_widgets.progress_bar(0, 9, 10, self.unicode)
        self.assertEqual(tui_style.strip_ansi(empty), "\u2500" * 10)

    def test_progress_bar_clamps(self) -> None:
        self.assertEqual(tui_style.strip_ansi(tui_widgets.progress_bar(20, 10, 6, self.unicode)), "\u2501" * 6)
        self.assertEqual(tui_style.strip_ansi(tui_widgets.progress_bar(1, 0, 4, self.unicode)), "\u2500" * 4)
        self.assertEqual(tui_widgets.progress_bar(1, 2, 0, self.unicode), "")

    def test_progress_bar_ascii(self) -> None:
        bar = tui_widgets.progress_bar(1, 2, 8, self.ascii)
        self.assertEqual(tui_style.display_width(bar), 8)
        self.assertEqual(tui_style.strip_ansi(bar), "####----")

    def test_columns_align_and_pad(self) -> None:
        lines = tui_widgets.columns(["a", "bb"], ["x"], gap=2)
        self.assertEqual(lines, ["a   x", "bb   "])
        self.assertEqual(tui_widgets.columns([], [], gap=2), [])
        self.assertEqual(tui_widgets.columns(["only"], [], gap=2), ["only"])

    def test_spinner(self) -> None:
        for frame in range(14):
            glyph = tui_widgets.spinner(frame, self.unicode)
            self.assertEqual(tui_style.display_width(glyph), 1)
            self.assertIn(glyph, tui_widgets._UNICODE_SPINNER)
        for frame in range(5):
            self.assertIn(tui_widgets.spinner(frame, self.ascii), "|/-\\")

    def test_key_hints_width_and_wrapping(self) -> None:
        pairs = [("up", "move"), ("space", "select"), ("q", "quit")]
        lines = tui_widgets.key_hints(pairs, 24, self.unicode)
        self.assertTrue(len(lines) >= 1)
        for line in lines:
            self.assertEqual(tui_style.display_width(line), 24)
        text = " ".join(tui_style.strip_ansi(line) for line in lines)
        self.assertIn("move", text)
        self.assertIn("quit", text)
        self.assertEqual(tui_widgets.key_hints([], 12, self.unicode), [" " * 12])
        self.assertEqual(tui_widgets.key_hints(pairs, 0, self.unicode), [])

    def test_key_hints_truncate_a_too_long_hint(self) -> None:
        lines = tui_widgets.key_hints([("ctrl-shift-enter", "do something unreasonably long")], 10, self.unicode)
        self.assertEqual(tui_style.display_width(lines[0]), 10)


@unittest.skipUnless(os.name == "posix", "needs a POSIX pty")
class TerminalTest(unittest.TestCase):
    """`Terminal` through a pty: raw mode, frames, key reads and restoration."""

    def setUp(self) -> None:
        import pty

        try:
            self.master, self.slave = pty.openpty()
        except OSError as error:  # pragma: no cover - no /dev/ptmx
            self.skipTest(f"pty unavailable: {error}")
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        self.stream = io.StringIO()

    def test_restores_on_exception(self) -> None:
        import termios

        before = termios.tcgetattr(self.slave)
        with self.assertRaises(RuntimeError):
            with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
                self.assertIsInstance(term, tui_terminal.Terminal)
                raw = termios.tcgetattr(self.slave)
                self.assertFalse(raw[3] & termios.ICANON, "canonical mode is off")
                self.assertFalse(raw[3] & termios.ECHO, "echo is off")
                raise RuntimeError("boom")
        self.assertEqual(termios.tcgetattr(self.slave), before)
        written = self.stream.getvalue()
        self.assertIn("\x1b[?1049h", written)
        self.assertIn("\x1b[?25l", written)
        self.assertIn("\x1b[?1049l", written)
        self.assertIn("\x1b[?25h", written)

    def test_restores_on_normal_exit(self) -> None:
        import termios

        before = termios.tcgetattr(self.slave)
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream):
            pass
        self.assertEqual(termios.tcgetattr(self.slave), before)

    def test_restore_is_idempotent(self) -> None:
        term = tui_terminal.Terminal(fd=self.slave, stream=self.stream)
        with term:
            pass
        term.restore()
        term.restore()

    def test_sigterm_handler_is_installed_and_restored(self) -> None:
        previous = signal.getsignal(signal.SIGTERM)
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream):
            self.assertNotEqual(signal.getsignal(signal.SIGTERM), previous)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_draw_writes_one_frame_and_skips_identical_ones(self) -> None:
        class RecordingStream:
            def __init__(self) -> None:
                self.writes = []

            def write(self, text: str) -> int:
                self.writes.append(text)
                return len(text)

            def flush(self) -> None:
                pass

        stream = RecordingStream()
        with tui_terminal.Terminal(fd=self.slave, stream=stream) as term:
            term.draw(["one", "two"])
            self.assertEqual(stream.writes[-1], "\x1b[Hone\x1b[K\r\ntwo\x1b[K\x1b[J")
            term.draw(["one", "two"])
            self.assertEqual(len(stream.writes), 2, "identical frame is not rewritten")
            term.draw(["three"])
            self.assertEqual(len(stream.writes), 3)
            term.draw([])
            self.assertEqual(stream.writes[-1], "\x1b[H\x1b[J")

    def test_read_key_reads_through_the_pty(self) -> None:
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
            os.write(self.master, b"\x1b[A")
            self.assertEqual(term.read_key(0.5), "up")
            os.write(self.master, b"\x7f")
            self.assertEqual(term.read_key(0.5), "backspace")
            os.write(self.master, b"X")
            self.assertEqual(term.read_key(0.5), "X")
            self.assertIsNone(term.read_key(0.05), "timeout without input")

    def test_read_key_returns_buffered_keys(self) -> None:
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
            os.write(self.master, b"ab")
            self.assertEqual(term.read_key(0.5), "a")
            self.assertEqual(term.read_key(0.5), "b")

    def test_read_key_completes_a_split_escape_sequence(self) -> None:
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
            os.write(self.master, b"\x1b")
            os.write(self.master, b"[B")
            self.assertEqual(term.read_key(0.5), "down")

    def test_lone_escape_is_esc_after_the_grace_period(self) -> None:
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
            start = time.monotonic()
            os.write(self.master, b"\x1b")
            self.assertEqual(term.read_key(0.5), "esc")
            elapsed = time.monotonic() - start
            self.assertGreaterEqual(elapsed, tui_terminal.ESCAPE_TIMEOUT * 0.5)
            self.assertLess(elapsed, 0.4)

    def test_size_reads_the_window(self) -> None:
        import fcntl
        import struct
        import termios

        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        term = tui_terminal.Terminal(fd=self.slave, stream=self.stream)
        size = term.size()
        self.assertEqual((size.columns, size.lines), (120, 40))
        width, height = size
        self.assertEqual((width, height), (120, 40))

    def test_size_falls_back_without_a_terminal(self) -> None:
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        size = tui_terminal.Terminal(fd=read_fd, stream=self.stream).size()
        self.assertGreater(size.columns, 0)
        self.assertGreater(size.lines, 0)


if __name__ == "__main__":
    unittest.main()
