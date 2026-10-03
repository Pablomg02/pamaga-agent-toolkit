"""Reusable TUI widgets: boxes, progress bar, columns, spinner, key hints.

Every function returns strings whose visible width (see
`style.display_width`) is exactly the requested width, so a screen can stack
and compose widgets without drift. Callers may pass pre-styled content; the
widgets measure it with ANSI sequences stripped.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from .style import Style, THEME, display_width, pad

# Default when a caller passes no style: no colour, ASCII glyphs.
PLAIN = Style("none", False)

_UNICODE_SPINNER = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
_ASCII_SPINNER = "|/-\\"


def _style_or_plain(style: Optional[Style]) -> Style:
    return PLAIN if style is None else style


def box(
    title: str,
    lines: Sequence[str],
    width: int,
    colour: str,
    style: Optional[Style] = None,
) -> List[str]:
    """A rounded box of exactly `width` columns with `title` in the top border.

    Returns the top border, one line per content line and the bottom border;
    longer content is truncated with an ellipsis, shorter content is padded.
    """
    style = _style_or_plain(style)
    if width <= 0:
        return []
    inner = max(0, width - 2)
    top_left = style.glyph("top_left")
    top_right = style.glyph("top_right")
    hline = style.glyph("hline")
    vline = style.glyph("vline")
    bottom = style.fg(
        style.glyph("bottom_left") + hline * inner + style.glyph("bottom_right"),
        colour,
    )
    label = style.truncate(title, max(0, inner - 2)) if inner >= 3 else ""
    if label:
        centre = " " + label + " " + hline * max(0, inner - display_width(label) - 2)
    else:
        centre = hline * inner
    top = style.fg(top_left + centre + top_right, colour)
    body = []
    for line in lines:
        body.append(style.fg(vline, colour) + " " + style.fit(line, max(0, inner - 1)) + style.fg(vline, colour))
    return [style.fit(top, width)] + [style.fit(line, width) for line in body] + [style.fit(bottom, width)]


def progress_bar(done: int, total: int, width: int, style: Optional[Style] = None) -> str:
    """A `width`-cell bar: filled in `build`, empty in `line`."""
    style = _style_or_plain(style)
    if width <= 0:
        return ""
    if total <= 0:
        filled = 0
    else:
        filled = int(done * width / total + 0.5)
    filled = max(0, min(width, filled))
    return (
        style.fg(style.glyph("bar_full") * filled, THEME["build"])
        + style.fg(style.glyph("bar_empty") * (width - filled), THEME["line"])
    )


def columns(left: Sequence[str], right: Sequence[str], gap: int = 2) -> List[str]:
    """Two text columns side by side, each line as wide as the widest line.

    Lines are padded with `style.pad`'s rules (ANSI-aware); missing lines on
    one side become spaces. The result width is the widest left line + `gap`
    + the widest right line; when one side is empty the other is returned as
    is, without the gap.
    """
    left = list(left)
    right = list(right)
    gap = max(0, gap)
    left_width = max((display_width(line) for line in left), default=0)
    right_width = max((display_width(line) for line in right), default=0)
    if not left or not right:
        gap = 0
    height = max(len(left), len(right))
    out = []
    for index in range(height):
        line = left[index] if index < len(left) else ""
        other = right[index] if index < len(right) else ""
        out.append(pad(line, left_width) + " " * gap + pad(other, right_width))
    return out


def spinner(frame: int, style: Optional[Style] = None) -> str:
    """One animation cell (a single-width glyph) for the given frame number."""
    style = _style_or_plain(style)
    frames = _UNICODE_SPINNER if style.unicode else _ASCII_SPINNER
    return frames[frame % len(frames)]


def key_hints(
    pairs: Iterable[Tuple[str, str]],
    width: int,
    style: Optional[Style] = None,
) -> List[str]:
    """Full-width footer lines with `key label` hints, wrapped at `width`.

    Hints are joined with two spaces and coloured `muted`; a hint that does
    not fit on its own is truncated with an ellipsis.
    """
    style = _style_or_plain(style)
    if width <= 0:
        return []
    chunks = [f"{key} {label}" for key, label in pairs]
    if not chunks:
        return [" " * width]
    lines = []
    current = ""
    for chunk in chunks:
        if not current:
            current = chunk
        elif display_width(current) + 2 + display_width(chunk) <= width:
            current += "  " + chunk
        else:
            lines.append(current)
            current = chunk
    lines.append(current)
    return [style.fg(style.fit(line, width), THEME["muted"]) for line in lines]
