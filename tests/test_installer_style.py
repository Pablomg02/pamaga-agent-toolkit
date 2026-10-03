"""Tests for the installer TUI primitives: style, widgets and terminal.

Key decoding, colour depth, text measurement and the widgets are pure and
tested directly; `Terminal` is exercised through a pty so raw mode, the
alternate screen, key reads and restoration are checked without the real
standard input.
"""

from __future__ import annotations

import io
import os
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

from installer.state import Status  # noqa: E402
from installer.tui import style as tui_style  # noqa: E402
from installer.tui import terminal as tui_terminal  # noqa: E402
from installer.tui import widgets as tui_widgets  # noqa: E402


class DecodeTest(unittest.TestCase):
    """`decode(bytes) -> list[str]`, the pure key decoder used by read_key."""

    def test_sequences(self) -> None:
        cases = {
            b"\x1b[A": ["up"], b"\x1b[B": ["down"], b"\x1b[C": ["right"], b"\x1b[D": ["left"],
            b"\x1bOA": ["up"], b"\x1bOB": ["down"], b"\x1bOC": ["right"], b"\x1bOD": ["left"],
            b"\x1b[5~": ["pgup"], b"\x1b[6~": ["pgdn"],
            b"\x1b[H": ["home"], b"\x1b[F": ["end"], b"\x1b[1~": ["home"], b"\x1b[4~": ["end"],
            b"\x1bOH": ["home"], b"\x1bOF": ["end"], b"\x1b[3~": ["delete"],
            b"\r": ["enter"], b"\n": ["enter"], b"\r\n": ["enter"],
            b"\x7f": ["backspace"], b"\x08": ["backspace"],
            b"\x03": ["ctrl-c"], b"\t": ["tab"], b" ": ["space"], b"\x1b": ["esc"],
            b"a": ["a"], b"/": ["/"], b"\xc3\xa9": ["é"],
            b"ab": ["a", "b"], b"\x1b[A\x1b[B": ["up", "down"], b"\x1b[5~\r": ["pgup", "enter"],
            b"\x01\x02": [],
        }
        for sequence, expected in cases.items():
            with self.subTest(sequence=sequence):
                keys = tui_terminal.decode(sequence)
                self.assertEqual(keys, expected)
                for key in keys:
                    if len(key) > 1:
                        self.assertIn(key, tui_terminal.KEY_NAMES)

    def test_windows_decoding(self) -> None:
        cases = {
            "\x00H": ["up"], "\xe0P": ["down"], "\x00K": ["left"], "\x00M": ["right"],
            "\x00I": ["pgup"], "\x00Q": ["pgdn"], "\x00G": ["home"], "\x00O": ["end"],
            "\r": ["enter"], "\x1b": ["esc"], "\t": ["tab"], "\x08": ["backspace"],
            " ": ["space"], "\x03": ["ctrl-c"], "a\x00M": ["a", "right"],
        }
        for chars, expected in cases.items():
            with self.subTest(chars=chars):
                self.assertEqual(tui_terminal.decode_windows(chars), expected)


class StyleTest(unittest.TestCase):
    """Colour depth detection, the no-colour contract and glyph fallbacks."""

    def test_depth_detection(self) -> None:
        cases = (
            ({"TERM": "xterm-256color", "COLORTERM": "truecolor"}, tui_style.DEPTH_TRUECOLOR),
            ({"TERM": "xterm-256color", "COLORTERM": "24bit"}, tui_style.DEPTH_TRUECOLOR),
            ({"TERM": "xterm-256color"}, tui_style.DEPTH_256),
            ({"TERM": "xterm"}, tui_style.DEPTH_16),
            ({}, tui_style.DEPTH_16),
            ({"TERM": "xterm", "NO_COLOR": "1", "COLORTERM": "truecolor"}, tui_style.DEPTH_NONE),
            ({"TERM": "xterm", "NO_COLOR": ""}, tui_style.DEPTH_16),
            ({"TERM": "dumb", "COLORTERM": "truecolor"}, tui_style.DEPTH_NONE),
        )
        for env, expected in cases:
            with self.subTest(env=env):
                self.assertEqual(tui_style.detect_depth(env), expected)
        self.assertEqual(tui_style.detect_depth({"TERM": "xterm-256color"}, no_color=True), tui_style.DEPTH_NONE)
        self.assertTrue(tui_style.Style.detect(env={"TERM": "xterm"}, encoding="UTF-8").unicode)
        self.assertFalse(tui_style.Style.detect(env={"TERM": "xterm"}, encoding="ascii").unicode)
        self.assertFalse(tui_style.Style.detect(env={"TERM": "xterm"}, ascii=True, encoding="utf-8").unicode)
        with self.assertRaises(ValueError):
            tui_style.Style("sepia")

    def test_no_colour_returns_text_unchanged(self) -> None:
        style = tui_style.Style(tui_style.DEPTH_NONE, True)
        for method in (style.bold, style.dim, style.italic, style.reverse):
            self.assertEqual(method("hello"), "hello")
        self.assertEqual(style.fg("hello", "#58a6ff"), "hello")
        self.assertEqual(style.bg("hello", "#58a6ff"), "hello")

    def test_colour_codes_per_depth(self) -> None:
        cases = (
            (tui_style.DEPTH_TRUECOLOR, r"\x1b\[38;2;88;166;255mx\x1b\[39m", r"\x1b\[48;2;88;166;255mx\x1b\[49m"),
            (tui_style.DEPTH_256, r"\x1b\[38;5;\d+mx\x1b\[39m", r"\x1b\[48;5;\d+mx\x1b\[49m"),
            (tui_style.DEPTH_16, r"\x1b\[(3\d|9\d)mx\x1b\[39m", r"\x1b\[(4\d|10\d)mx\x1b\[49m"),
        )
        for depth, fg, bg in cases:
            with self.subTest(depth=depth):
                style = tui_style.Style(depth, True)
                self.assertRegex(style.fg("x", "#58a6ff"), "^" + fg + "$")
                self.assertRegex(style.bg("x", "#58a6ff"), "^" + bg + "$")

    def test_every_status_has_a_glyph_in_both_modes(self) -> None:
        for status in Status:
            with self.subTest(status=status.value):
                self.assertTrue(tui_style.glyph(status.value))
                self.assertTrue(tui_style.glyph(status.value, unicode=False).isascii())
        for name, char in tui_style.UNICODE_GLYPHS.items():
            with self.subTest(name=name):
                self.assertEqual(tui_style.display_width(char), 1, "Unicode glyphs are one cell wide")
                self.assertTrue(tui_style.glyph(name, unicode=False).isascii())
        with self.assertRaises(KeyError):
            tui_style.glyph("banana")


class TextTest(unittest.TestCase):
    """Width measurement, truncate, pad and wrap never break the layout."""

    SAMPLES = (
        "hello world",
        "\x1b[31mhello world\x1b[0m",
        "日本語です",
        "\x1b[1m日本語\x1b[22m",
        "▸ ◉ make-plan ↑",
        "",
    )

    def test_display_width(self) -> None:
        self.assertEqual(tui_style.display_width("hello"), 5)
        self.assertEqual(tui_style.display_width("\x1b[38;2;1;2;3mx\x1b[39m\x1b[K"), 1, "ANSI is zero width")
        self.assertEqual(tui_style.display_width("日本"), 4, "CJK is two cells")
        self.assertEqual(tui_style.display_width("é"), 1, "combining marks are zero width")

    def test_truncate(self) -> None:
        for text in self.SAMPLES:
            for width in range(0, 14):
                with self.subTest(text=text, width=width):
                    self.assertLessEqual(tui_style.display_width(tui_style.truncate(text, width)), width)
        self.assertEqual(tui_style.truncate("\x1b[31mhello\x1b[0m", 5), "\x1b[31mhello\x1b[0m")
        self.assertEqual(tui_style.truncate("hello world", 6), "hello…")
        self.assertEqual(tui_style.truncate("日本語", 4), "日…")
        self.assertTrue(tui_style.truncate("\x1b[31mhello world\x1b[0m", 8).endswith("\x1b[0m"),
                        "open styles are closed")
        self.assertNotIn("\x1b", tui_style.truncate("hello world", 8))
        self.assertEqual(tui_style.Style(tui_style.DEPTH_NONE, False).truncate("hello world", 6), "hel...")

    def test_pad_and_fit(self) -> None:
        self.assertEqual(tui_style.pad("\x1b[31mab\x1b[0m", 4), "\x1b[31mab\x1b[0m  ")
        self.assertEqual(tui_style.pad("abcd", 2), "abcd")
        self.assertEqual(tui_style.display_width(tui_style.pad("日", 5)), 5)
        style = tui_style.Style(tui_style.DEPTH_16, True)
        for text in self.SAMPLES:
            with self.subTest(text=text):
                self.assertEqual(tui_style.display_width(style.fit(text, 5)), 5)

    def test_wrap(self) -> None:
        self.assertEqual(tui_style.wrap("one two three", 7), ["one two", "three"])
        self.assertEqual(tui_style.wrap("one twothree", 3), ["one", "two", "thr", "ee"])
        self.assertEqual(tui_style.wrap("a\n\nb", 5), ["a", "", "b"])
        self.assertEqual(tui_style.wrap("\x1b[1mhello\x1b[0m world", 5), ["\x1b[1mhello\x1b[0m", "world"])
        self.assertEqual(tui_style.wrap("日", 1), ["日"], "a wide character cannot be split")
        self.assertEqual(tui_style.wrap("hello", 0), [])
        text = "the quick brown fox 日本語 jumps over the lazy dog"
        for width in range(2, 12):
            with self.subTest(width=width):
                for line in tui_style.wrap(text, width):
                    self.assertLessEqual(tui_style.display_width(line), width)


class WidgetsTest(unittest.TestCase):
    """Every widget renders exactly the requested width."""

    def setUp(self) -> None:
        self.unicode = tui_style.Style(tui_style.DEPTH_NONE, True)
        self.ascii = tui_style.Style(tui_style.DEPTH_NONE, False)

    def test_box(self) -> None:
        styled = self.unicode.fg("modificado", tui_style.THEME["keep"])
        for style in (self.unicode, self.ascii):
            for width in (1, 2, 3, 4, 8, 20, 61):
                with self.subTest(unicode=style.unicode, width=width):
                    lines = tui_widgets.box("Skills", ["make-plan", "long line " * 8, styled],
                                            width, tui_style.THEME["think"], style)
                    for line in lines:
                        self.assertEqual(tui_style.display_width(line), width)
                        if not style.unicode:
                            self.assertTrue(tui_style.strip_ansi(line).isascii(), line)
        self.assertEqual(tui_widgets.box("x", [], 0, "#ffffff", self.unicode), [])

    def test_progress_bar(self) -> None:
        self.assertEqual(tui_style.display_width(tui_widgets.progress_bar(3, 10, 20, self.unicode)), 20)
        self.assertEqual(tui_style.strip_ansi(tui_widgets.progress_bar(20, 10, 6, self.unicode)), "━" * 6)
        self.assertEqual(tui_style.strip_ansi(tui_widgets.progress_bar(1, 0, 4, self.unicode)), "─" * 4)
        self.assertEqual(tui_widgets.progress_bar(1, 2, 0, self.unicode), "")
        self.assertEqual(tui_style.strip_ansi(tui_widgets.progress_bar(1, 2, 8, self.ascii)), "####----")

    def test_columns_and_spinner(self) -> None:
        self.assertEqual(tui_widgets.columns(["a", "bb"], ["x"], gap=2), ["a   x", "bb   "])
        self.assertEqual(tui_widgets.columns([], [], gap=2), [])
        for frame in range(14):
            self.assertEqual(tui_style.display_width(tui_widgets.spinner(frame, self.unicode)), 1)
            self.assertIn(tui_widgets.spinner(frame, self.ascii), "|/-\\")

    def test_key_hints(self) -> None:
        pairs = [("up", "move"), ("space", "select"), ("q", "quit")]
        lines = tui_widgets.key_hints(pairs, 24, self.unicode)
        for line in lines:
            self.assertEqual(tui_style.display_width(line), 24)
        self.assertIn("quit", " ".join(tui_style.strip_ansi(line) for line in lines))
        long = tui_widgets.key_hints([("ctrl-shift-enter", "do something unreasonably long")], 10, self.unicode)
        self.assertEqual(tui_style.display_width(long[0]), 10)
        self.assertEqual(tui_widgets.key_hints(pairs, 0, self.unicode), [])


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

    def attrs(self) -> list:
        """The pty's termios attributes without PENDIN, which macOS sets on
        its own when canonical mode comes back."""
        import termios

        attrs = termios.tcgetattr(self.slave)
        attrs[3] &= ~getattr(termios, "PENDIN", 0)
        return attrs

    def test_restores_on_exception(self) -> None:
        import termios

        before = self.attrs()
        with self.assertRaises(RuntimeError):
            with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
                self.assertIsInstance(term, tui_terminal.Terminal)
                raw = termios.tcgetattr(self.slave)
                self.assertFalse(raw[3] & termios.ICANON, "canonical mode is off")
                self.assertFalse(raw[3] & termios.ECHO, "echo is off")
                raise RuntimeError("boom")
        self.assertEqual(self.attrs(), before)
        written = self.stream.getvalue()
        self.assertIn("\x1b[?1049h", written)
        self.assertIn("\x1b[?25l", written)
        self.assertIn("\x1b[?1049l", written)
        self.assertIn("\x1b[?25h", written)

    def test_restores_on_normal_exit(self) -> None:
        before = self.attrs()
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream):
            pass
        self.assertEqual(self.attrs(), before)

    def test_keeps_a_key_typed_before_raw_mode(self) -> None:
        os.write(self.master, b"q")
        with tui_terminal.Terminal(fd=self.slave, stream=self.stream) as term:
            self.assertEqual(term.read_key(1.0), "q")

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

    def test_size_falls_back_for_an_unsized_pty(self) -> None:
        # A fresh pty reports 0x0; before Python 3.11 shutil passed that on.
        from unittest import mock

        term = tui_terminal.Terminal(fd=self.slave, stream=self.stream)
        with mock.patch.object(tui_terminal.shutil, "get_terminal_size", return_value=os.terminal_size((0, 0))):
            size = term.size()
        self.assertEqual((size.columns, size.lines), tui_terminal.DEFAULT_SIZE)


if __name__ == "__main__":
    unittest.main()
