"""The macaque mascot and the "PAMAGA AGENT TOOLKIT" wordmark.

The mascot is pixel art rendered with half-block characters: each text row
shows two pixel rows, the upper pixel as the foreground and the lower as the
background of `\\u2580`. Truecolour terminals get the full palette, Unicode
terminals without colour get the block art, and anything less falls back to a
hand-drawn `MACAQUE_ASCII` face. The wordmark uses a small 5-row block font,
graded left to right through the workflow stage colours in truecolour and
letter by letter in 256/16 colours.

Run it straight to look at it: `python3 -m installer.tui.logo` (from
`scripts/`), optionally with `--ascii` or `--no-color`.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import shutil
import sys
from typing import List, Optional, Sequence

from .style import (DEPTH_16, DEPTH_256, DEPTH_NONE, DEPTH_TRUECOLOR, STAGES, Style,
                    display_width, hex_to_rgb, pad, rgb_to_hex, stage_colour)

TAGLINE = "Macaco giving macacos instructions"

# One character per pixel; "." is transparent, every other key is in PALETTE.
# 32 columns x 30 rows (an even number, so half blocks pair up exactly).
MACAQUE: List[str] = [
    ".............OOOOOO.............",
    "...........OOFFFFFFOO...........",
    ".........OOFLLLLLLLLFOO.........",
    "........OFFLLLLLLLLLLFFO........",
    "........OFLLLLLLLLLLLLFO........",
    "....OOOOFFFFFFFFFFFFFFFFOOOO....",
    "..OOFFFFFFFFFRRRRRRFFFFFFFFFOO..",
    "..OFFFFFFFFRRSSSSSSRRFFFFFFFFO..",
    ".OFFFFFFFFRREEWSSEEWRRFFFFFFFFO.",
    ".OFFRRRFFFRSEEESSEEESRFFFRRRFFO.",
    ".OFFRRRFFRSSEEESSEEESSRFFRRRFFO.",
    ".OFFFFFFFRSSEEESSEEESSRFFFFFFFO.",
    "..OFFFFFFRSSSSSSSSSSSSRFFFFFFO..",
    "..OOFFFFFRSSSSSSSSSSSSRFFFFFOO..",
    "....OOOFFRSSSSMSSMSSSSRFFOOO....",
    ".......OFRSSSSSSSSSSSSRFO.......",
    "........OFRSSMSSSSMSSRFO........",
    "........OFRRSSMMMMSSRRFO........",
    ".........OORRSSSSSSRROO.........",
    "...........OFRRRRRRFO...........",
    "...........OFFFFFFFFO...........",
    "...........OFFFFFFFFO...........",
    "...........OFFFFFFFFO...........",
    ".........OOFFFFFFFFFFOO.........",
    "......OOOFFFFFFFFFFFFFFOOO......",
    "....OOFFFFFFFFFFFFFFFFFFFFOO....",
    "...OFFFFFFFFFFFFFFFFFFFFFFFFO...",
    ".OOFFFFFFFFFFFFFFFFFFFFFFFFFFOO.",
    "OFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFO",
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
]

PALETTE = {
    "O": "#3b2414",  # outline
    "F": "#a0673a",  # fur
    "L": "#c98a52",  # light fur
    "S": "#f0a08c",  # skin
    "R": "#e0705e",  # red (face mask rim, ears, cheeks)
    "E": "#1b1b1b",  # eyes and closed lids
    "W": "#ffffff",  # eye highlight
    "M": "#7a2e2e",  # nostrils and mouth
}

# Eye regions as half-open (row_start, row_end, col_start, col_end) boxes.
# Each box holds exactly one open eye's `E`/`W` pixels (tests check this).
EYE_BOXES = ((8, 12, 12, 15), (8, 12, 17, 20))
# Pixel row of the closed lid, inside the eye rows above.
CLOSED_EYE_ROW = 10


def _closed_eyes(grid: Sequence[str]) -> List[str]:
    """The same grid with the eyes shut: each eye is skin with one lid line."""
    out = [list(row) for row in grid]
    for row_start, row_end, col_start, col_end in EYE_BOXES:
        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                out[row][col] = "E" if row == CLOSED_EYE_ROW else "S"
    return ["".join(row) for row in out]


MACAQUE_BLINK: List[str] = _closed_eyes(MACAQUE)

# Hand-drawn fallback for terminals without colour or without Unicode: at most
# 24x10, printable ASCII only.
MACAQUE_ASCII: List[str] = [
    "    .-''-''-.",
    "   .'       '.",
    " /   _     _   \\",
    "(   (o)   (o)   )",
    " \\      .      /",
    "  |  \\_____/  |",
    "   '.       .'",
    "     '--.--'",
]

# Five rows per glyph; only the letters the two wordmark lines need.
BLOCK_FONT = {
    "A": [".##.", "#..#", "####", "#..#", "#..#"],
    "E": ["####", "#...", "###.", "#...", "####"],
    "G": [".###", "#...", "#.##", "#..#", ".###"],
    "I": ["####", ".##.", ".##.", ".##.", "####"],
    "K": ["#..#", "#.#.", "##..", "#.#.", "#..#"],
    "L": ["#...", "#...", "#...", "#...", "####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
    "N": ["#..#", "##.#", "#.##", "#..#", "#..#"],
    "O": [".##.", "#..#", "#..#", "#..#", ".##."],
    "P": ["####", "#..#", "####", "#...", "#..."],
    "T": ["####", ".##.", ".##.", ".##.", ".##."],
    " ": ["..", "..", "..", "..", ".."],
}
BLOCK_ROWS = 5
WORDMARK = ("PAMAGA", "AGENT TOOLKIT")
WORDMARK_FALLBACK = "PAMAGA AGENT TOOLKIT"


def _word_width(word: str) -> int:
    return sum(max(len(row) for row in BLOCK_FONT[letter]) for letter in word) + len(word) - 1


def _gradient(position: float) -> str:
    """A hex colour `position` (0..1) along think -> build -> check -> deliver -> keep."""
    stops = [hex_to_rgb(stage_colour(stage)) for stage in STAGES]
    location = max(0.0, min(1.0, position)) * (len(stops) - 1)
    index = min(int(location), len(stops) - 2)
    fraction = location - index
    start, end = stops[index], stops[index + 1]
    rgb = tuple(round(start[channel] + (end[channel] - start[channel]) * fraction) for channel in range(3))
    return rgb_to_hex(rgb)


def render_logo(style: Style, blink: bool = False) -> List[str]:
    """The macaque as terminal lines.

    Depth `none` or a non-Unicode terminal yields the ASCII face; otherwise
    each line is two pixel rows of half blocks, at most 32 columns and 16
    lines. `blink` uses the closed-eye grid.
    """
    if style.depth == DEPTH_NONE or not style.unicode:
        return list(MACAQUE_ASCII)
    grid = MACAQUE_BLINK if blink else MACAQUE
    lines: List[str] = []
    for row in range(0, len(grid) - 1, 2):
        top, bottom = grid[row], grid[row + 1]
        cells = []
        for column in range(len(top)):
            top_pixel, bottom_pixel = top[column], bottom[column]
            if top_pixel == "." and bottom_pixel == ".":
                cells.append(" ")
            elif top_pixel == ".":
                cells.append(style.fg("\u2584", PALETTE[bottom_pixel]))
            elif bottom_pixel == ".":
                cells.append(style.fg("\u2580", PALETTE[top_pixel]))
            else:
                cells.append(style.fg(style.bg("\u2580", PALETTE[bottom_pixel]), PALETTE[top_pixel]))
        lines.append("".join(cells).rstrip() + "\x1b[0m")
    return lines


def _cell_colour(style: Style, column: int, letter: int, block_width: int) -> Optional[str]:
    if style.depth == DEPTH_TRUECOLOR:
        return _gradient(column / max(1, block_width - 1))
    if style.depth in (DEPTH_16, DEPTH_256):
        return stage_colour(STAGES[letter % len(STAGES)])
    return None


def render_wordmark(style: Style, max_width: int) -> List[str]:
    """The two-line wordmark, or one bold line when it does not fit `max_width`.

    Line one is `PAMAGA` centred over `AGENT TOOLKIT`; letters are five rows
    of `\\u2588` (ASCII mode: `#`). Truecolour grades the columns through the
    stage colours; 256/16 colours give each letter the next stage colour.
    """
    widths = [_word_width(word) for word in WORDMARK]
    block_width = max(widths)
    if max_width < block_width or block_width <= 0:
        return [style.truncate(style.bold(WORDMARK_FALLBACK), max_width)]
    char = "\u2588" if style.unicode else "#"
    lines: List[str] = []
    letter_index = 0
    for word, word_width in zip(WORDMARK, widths):
        offset = (block_width - word_width) // 2
        for row in range(BLOCK_ROWS):
            cells = [" "] * offset  # centre the shorter word over the longer one
            column = offset
            index = letter_index
            first = True
            for letter in word:
                if not first:
                    cells.append(" ")  # one column of letter spacing
                    column += 1
                first = False
                for pixel in BLOCK_FONT[letter][row]:
                    if pixel == "#":
                        colour = _cell_colour(style, column, index, block_width)
                        cells.append(style.fg(char, colour) if colour else char)
                    else:
                        cells.append(" ")
                    column += 1
                if letter != " ":
                    index += 1
            lines.append("".join(cells))
        letter_index += sum(1 for letter in word if letter != " ")
    return lines


# -- the script-free preview ------------------------------------------------


def _side_by_side(left: Sequence[str], right: Sequence[str], gap: int = 2) -> List[str]:
    left_width = max((display_width(line) for line in left), default=0)
    height = max(len(left), len(right))
    top = (height - len(right)) // 2
    lines = []
    for index in range(height):
        line = pad(left[index] if index < len(left) else "", left_width)
        other = index - top
        if 0 <= other < len(right):
            line += " " * gap + right[other]
        lines.append(line.rstrip())
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    """Print the logo, the wordmark and the tagline for the current terminal."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    style = Style.detect(ascii="--ascii" in arguments, no_color="--no-color" in arguments)
    width = shutil.get_terminal_size(fallback=(80, 24)).columns
    logo = render_logo(style)
    wordmark = render_wordmark(style, max(20, width - 6))
    if width >= 100:
        lines = _side_by_side(logo, wordmark)
    else:
        lines = logo + [""] + wordmark
    lines += ["", style.italic(TAGLINE)]
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
