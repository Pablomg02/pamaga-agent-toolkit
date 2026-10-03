"""ANSI colours, text measurement and glyph fallbacks for the installer TUI.

`Style` decides how text is decorated for one terminal: colour depth (`none`,
`16`, `256`, `truecolor`) and whether Unicode glyphs are available. Everything
else in this module is pure text handling -- measuring, truncating, padding,
wrapping -- so it is fully testable without a terminal.

`THEME` is also the dark theme of the README diagram drawn by
`scripts/draw_workflow.py`, so both always agree.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from typing import Iterator, Mapping, Optional, Tuple

DEPTH_NONE = "none"
DEPTH_16 = "16"
DEPTH_256 = "256"
DEPTH_TRUECOLOR = "truecolor"
DEPTHS = (DEPTH_NONE, DEPTH_16, DEPTH_256, DEPTH_TRUECOLOR)

# Also the README diagram's dark theme (scripts/draw_workflow.py imports it).
THEME = {
    "text": "#e6edf3",
    "muted": "#9198a1",
    "line": "#6e7681",
    "bg": "#0d1117",
    "think": "#58a6ff",
    "build": "#3fb950",
    "check": "#f0883e",
    "deliver": "#a371f7",
    "keep": "#f778ba",
}

# Stage names in workflow order; `support` and anything unknown fall back to muted.
STAGES = ("think", "build", "check", "deliver", "keep")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

_ANSI16_RGB = (
    (0x00, 0x00, 0x00), (0x80, 0x00, 0x00), (0x00, 0x80, 0x00), (0x80, 0x80, 0x00),
    (0x00, 0x00, 0x80), (0x80, 0x00, 0x80), (0x00, 0x80, 0x80), (0xc0, 0xc0, 0xc0),
    (0x80, 0x80, 0x80), (0xff, 0x00, 0x00), (0x00, 0xff, 0x00), (0xff, 0xff, 0x00),
    (0x00, 0x00, 0xff), (0xff, 0x00, 0xff), (0x00, 0xff, 0xff), (0xff, 0xff, 0xff),
)


def _xterm256_rgb() -> Tuple[Tuple[int, int, int], ...]:
    palette = list(_ANSI16_RGB)
    levels = (0, 95, 135, 175, 215, 255)
    for red in levels:
        for green in levels:
            for blue in levels:
                palette.append((red, green, blue))
    for index in range(24):
        grey = 8 + index * 10
        palette.append((grey, grey, grey))
    return tuple(palette)


_XTERM256_RGB = _xterm256_rgb()

# Glyphs are all one cell wide; the ASCII column is the fallback when the
# terminal cannot show Unicode (see the TUI specification's glyph table).
UNICODE_GLYPHS = {
    "top_left": "\u256d",
    "top_right": "\u256e",
    "bottom_left": "\u2570",
    "bottom_right": "\u256f",
    "hline": "\u2500",
    "vline": "\u2502",
    "arrow": "\u25b8",
    "checkbox_on": "\u25c9",
    "checkbox_off": "\u25cb",
    "linked": "\u21c4",
    "up_to_date": "\u25cf",
    "outdated": "\u2191",
    "modified": "\u270e",
    "unmanaged": "!",
    "foreign_link": "!",
    "orphaned": "\u2717",
    "not_installed": "\u25cb",
    "ok": "\u2713",
    "fail": "\u2717",
    "bar_full": "\u2501",
    "bar_empty": "\u2500",
    "dot": "\u00b7",
    "gt": "\u203a",
    "lt": "\u2039",
}

ASCII_GLYPHS = {
    "top_left": "+",
    "top_right": "+",
    "bottom_left": "+",
    "bottom_right": "+",
    "hline": "-",
    "vline": "|",
    "arrow": ">",
    "checkbox_on": "[x]",
    "checkbox_off": "[ ]",
    "linked": "=",
    "up_to_date": "*",
    "outdated": "^",
    "modified": "~",
    "unmanaged": "!",
    "foreign_link": "!",
    "orphaned": "x",
    "not_installed": ".",
    "ok": "+",
    "fail": "x",
    "bar_full": "#",
    "bar_empty": "-",
    "dot": "-",
    "gt": ">",
    "lt": "<",
}


def glyph(name: str, unicode: bool = True) -> str:
    """The glyph called `name`, Unicode or its ASCII fallback.

    Status names accept both spellings of the `state.Status` values
    (`up-to-date` and `up_to_date`).
    """
    table = UNICODE_GLYPHS if unicode else ASCII_GLYPHS
    key = name.replace("-", "_")
    try:
        return table[key]
    except KeyError:
        raise KeyError(f"unknown glyph {name!r}; known: {', '.join(sorted(table))}") from None


def stage_colour(stage: str) -> str:
    """Hex colour of a workflow stage; `support` and unknown stages are muted."""
    return THEME.get(stage, THEME["muted"])


def hex_to_rgb(colour: str) -> Tuple[int, int, int]:
    """`#rgb` or `#rrggbb` to an (r, g, b) tuple."""
    value = colour.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        raise ValueError(f"not a hex colour: {colour!r}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """(r, g, b) to `#rrggbb`."""
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(value)))) for value in rgb)


def _nearest(rgb: Tuple[int, int, int], palette: Tuple[Tuple[int, int, int], ...]) -> int:
    red, green, blue = rgb
    best, best_distance = 0, None
    for index, (pred, pgreen, pblue) in enumerate(palette):
        distance = (red - pred) ** 2 + (green - pgreen) ** 2 + (blue - pblue) ** 2
        if best_distance is None or distance < best_distance:
            best, best_distance = index, distance
    return best


def detect_depth(env: Optional[Mapping[str, str]] = None, no_color: bool = False) -> str:
    """Colour depth for an environment mapping (defaults to `os.environ`).

    `none` when `no_color` is set, `NO_COLOR` is set to a non-empty value or
    `TERM=dumb`; `truecolor` when `COLORTERM` says so; `256` when `TERM`
    contains `256color`; `16` otherwise.
    """
    env = os.environ if env is None else env
    if no_color or env.get("NO_COLOR"):
        return DEPTH_NONE
    term = env.get("TERM", "")
    if term == "dumb":
        return DEPTH_NONE
    if env.get("COLORTERM", "") in ("truecolor", "24bit"):
        return DEPTH_TRUECOLOR
    if "256color" in term:
        return DEPTH_256
    return DEPTH_16


def strip_ansi(text: str) -> str:
    """Drop every ANSI escape sequence from `text`."""
    return ANSI_RE.sub("", text)


def _char_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    """Visible width of `text`: ANSI sequences are zero width, CJK is two cells."""
    return sum(_char_width(char) for char in strip_ansi(text))


def _tokens(text: str) -> Iterator[Tuple[bool, str]]:
    """Yield (is_ansi, token); non-ANSI tokens are single characters."""
    position = 0
    while position < len(text):
        match = ANSI_RE.match(text, position)
        if match:
            yield True, match.group(0)
            position = match.end()
            continue
        yield False, text[position]
        position += 1


def _take(text: str, width: int) -> str:
    """Longest prefix of `text` no wider than `width` (ANSI-aware)."""
    out = []
    used = 0
    for is_ansi, token in _tokens(text):
        if is_ansi:
            out.append(token)
            continue
        token_width = _char_width(token)
        if used + token_width > width:
            break
        out.append(token)
        used += token_width
    return "".join(out)


def truncate(text: str, width: int, ellipsis: str = "\u2026") -> str:
    """`text` cut to `width` visible cells, appending `ellipsis` when cut.

    Never wider than `width` (measured with `display_width`), and any style
    left open by the cut is closed with `\\x1b[0m`.
    """
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    ellipsis_width = display_width(ellipsis)
    if ellipsis_width > width:
        return _take(ellipsis, width)
    limit = width - ellipsis_width
    out = []
    used = 0
    styled = False
    for is_ansi, token in _tokens(text):
        if is_ansi:
            out.append(token)
            styled = True
            continue
        token_width = _char_width(token)
        if used + token_width > limit:
            break
        out.append(token)
        used += token_width
    result = "".join(out) + ellipsis
    if styled:
        result += "\x1b[0m"
    return result


def pad(text: str, width: int) -> str:
    """`text` plus spaces up to `width` cells; wider text is returned as is."""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    return text + " " * gap


def _hard_split(text: str, width: int) -> list:
    """Split one over-long word into lines of at most `width` cells."""
    pieces = []
    current = []
    used = 0
    for is_ansi, token in _tokens(text):
        if is_ansi:
            current.append(token)
            continue
        token_width = _char_width(token)
        if used and used + token_width > width:
            pieces.append("".join(current))
            current = []
            used = 0
        current.append(token)
        used += token_width
    pieces.append("".join(current))
    return pieces


def wrap(text: str, width: int) -> list:
    """Greedy word wrap of `text` to lines of at most `width` cells.

    Explicit newlines start a new line; runs of spaces collapse; a word wider
    than `width` is hard-split (a single double-width character may still
    exceed a width of 1, since it cannot be cut in half).
    """
    if width <= 0:
        return []
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        current = ""
        current_width = 0
        for word in words:
            word_width = display_width(word)
            if current:
                if current_width + 1 + word_width <= width:
                    current += " " + word
                    current_width += 1 + word_width
                    continue
                lines.append(current)
                current = ""
                current_width = 0
            if word_width <= width:
                current = word
                current_width = word_width
            else:
                pieces = _hard_split(word, width)
                lines.extend(pieces[:-1])
                current = pieces[-1]
                current_width = display_width(current)
        if current or not words:
            lines.append(current)
    return lines


class Style:
    """How one terminal wants its text decorated.

    `depth` is one of `DEPTHS` and `unicode` selects glyphs. Both come from
    `Style.detect()` in real use; tests and screens use the constructor.
    """

    def __init__(self, depth: str = DEPTH_TRUECOLOR, unicode: bool = True) -> None:
        if depth not in DEPTHS:
            raise ValueError(f"unknown colour depth {depth!r}; expected one of {', '.join(DEPTHS)}")
        self.depth = depth
        self.unicode = unicode

    @classmethod
    def detect(
        cls,
        env: Optional[Mapping[str, str]] = None,
        no_color: bool = False,
        ascii: bool = False,
        encoding: Optional[str] = None,
    ) -> "Style":
        """Style for the current process: environment colour, output encoding.

        `ascii` forces the ASCII glyphs; otherwise a `stdout` encoding that is
        not UTF-8 also falls back to them.
        """
        if encoding is None:
            encoding = getattr(sys.stdout, "encoding", None)
        unicode_ok = not ascii and (not encoding or "utf" in encoding.lower())
        return cls(detect_depth(env, no_color=no_color), unicode=unicode_ok)

    @property
    def coloured(self) -> bool:
        """True when colour escapes are written (`depth` is not `none`)."""
        return self.depth != DEPTH_NONE

    def _fg_code(self, colour: str) -> str:
        rgb = hex_to_rgb(colour)
        if self.depth == DEPTH_TRUECOLOR:
            return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"
        if self.depth == DEPTH_256:
            return f"\x1b[38;5;{_nearest(rgb, _XTERM256_RGB)}m"
        if self.depth == DEPTH_16:
            index = _nearest(rgb, _ANSI16_RGB)
            return f"\x1b[{30 + index if index < 8 else 90 + index - 8}m"
        return ""

    def _bg_code(self, colour: str) -> str:
        rgb = hex_to_rgb(colour)
        if self.depth == DEPTH_TRUECOLOR:
            return f"\x1b[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"
        if self.depth == DEPTH_256:
            return f"\x1b[48;5;{_nearest(rgb, _XTERM256_RGB)}m"
        if self.depth == DEPTH_16:
            index = _nearest(rgb, _ANSI16_RGB)
            return f"\x1b[{40 + index if index < 8 else 100 + index - 8}m"
        return ""

    def fg(self, text: str, colour: str) -> str:
        """`text` in a foreground colour; unchanged at depth `none`."""
        if self.depth == DEPTH_NONE:
            return text
        code = self._fg_code(colour)
        if not code:
            return text
        return f"{code}{text}\x1b[39m"

    def bg(self, text: str, colour: str) -> str:
        """`text` on a background colour; unchanged at depth `none`."""
        if self.depth == DEPTH_NONE:
            return text
        code = self._bg_code(colour)
        if not code:
            return text
        return f"{code}{text}\x1b[49m"

    def _attribute(self, text: str, code: str, reset: str) -> str:
        if self.depth == DEPTH_NONE:
            return text
        return f"{code}{text}{reset}"

    def bold(self, text: str) -> str:
        return self._attribute(text, "\x1b[1m", "\x1b[22m")

    def dim(self, text: str) -> str:
        return self._attribute(text, "\x1b[2m", "\x1b[22m")

    def italic(self, text: str) -> str:
        return self._attribute(text, "\x1b[3m", "\x1b[23m")

    def reverse(self, text: str) -> str:
        return self._attribute(text, "\x1b[7m", "\x1b[27m")

    def glyph(self, name: str) -> str:
        """`glyph(name)` for this terminal's Unicode policy."""
        return glyph(name, unicode=self.unicode)

    def truncate(self, text: str, width: int) -> str:
        """`truncate` with an ellipsis this terminal can show."""
        return truncate(text, width, ellipsis="\u2026" if self.unicode else "...")

    def fit(self, text: str, width: int) -> str:
        """`text` exactly `width` cells wide: truncated first, then padded."""
        return pad(self.truncate(text, width), width)
