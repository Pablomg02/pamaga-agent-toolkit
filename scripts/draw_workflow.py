#!/usr/bin/env python3
"""Draw the README workflow diagram as SVG, one file per GitHub theme.

The README shows images/workflow-light.svg or images/workflow-dark.svg
through a <picture> element. Edit NODES and EDGES below when the skills
change, then regenerate:

    python3 scripts/draw_workflow.py          # write both files
    python3 scripts/draw_workflow.py --check  # exit 1 if they are outdated

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IMAGES = Path(__file__).resolve().parent.parent / "images"

THEMES = {
    "light": dict(text="#1f2328", muted="#59636e", line="#8c959f", bg="#ffffff",
                  think="#2563eb", build="#059669", check="#c2410c", deliver="#7c3aed", keep="#db2777"),
    "dark": dict(text="#e6edf3", muted="#9198a1", line="#6e7681", bg="#0d1117",
                 think="#58a6ff", build="#3fb950", check="#f0883e", deliver="#a371f7", keep="#f778ba"),
}

SANS = "ui-sans-serif, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"
WIDTH, HEIGHT = 990, 400
W, H = 150, 60                          # node size
COL = [40, 230, 420, 610, 800]          # left x of each column
ROW = {"top": 64, "main": 176, "bottom": 296}

# Stage headers: label, first column, last column, colour.
STAGES = [("THINK", 0, 1, "think"), ("BUILD", 2, 2, "build"), ("CHECK", 3, 3, "check"), ("DELIVER", 4, 4, "deliver")]

# name: column, row, colour, subtitle, kind (core | optional | side)
NODES = {
    "research-topic": (0, "top", "think", "answers with evidence", "side"),
    "new-ticket": (1, "top", "think", "capture for later", "side"),
    "make-roadmap": (0, "main", "think", "milestones · optional", "optional"),
    "make-plan": (1, "main", "think", "reviewed plan.md", "core"),
    "implement-plan": (2, "main", "build", "subagents + verifier", "core"),
    "deep-review": (3, "main", "check", "a reviewer per theme", "core"),
    "ship-work": (4, "main", "deliver", "commit · push · PR", "core"),
    "plan-page": (1, "bottom", "think", "HTML explainer", "side"),
    "find-bug": (2, "bottom", "build", "root cause + test", "side"),
    "save-learning": (3, "bottom", "keep", "docs/learnings/", "side"),
}

DASH = {
    "solid": "",
    "dashed": ' stroke-dasharray="5 4"',
    "dotted": ' stroke-dasharray="1.5 4" stroke-linecap="round"',
}


def point(name: str, side: str, shift: float = 0) -> tuple[float, float]:
    """A point on a node's edge: l, r, t or b, moved along that edge by shift."""
    column, row, *_ = NODES[name]
    x, y = COL[column], ROW[row]
    return {
        "l": (x, y + H / 2 + shift),
        "r": (x + W, y + H / 2 + shift),
        "t": (x + W / 2 + shift, y),
        "b": (x + W / 2 + shift, y + H),
    }[side]


def edges() -> list[tuple[list[tuple[float, float]], str, str | None, tuple[float, float, str] | None]]:
    """Each edge: points of the path, style, label, label position (x, y, anchor)."""
    found_bug = point("find-bug", "b")
    ship = point("ship-work", "b")
    detour = found_bug[1] + 30
    return [
        ([point("research-topic", "b"), point("make-roadmap", "t")], "dashed", "informs", None),
        ([point("research-topic", "b", 55), point("make-plan", "t", -53)], "dashed", None, None),
        ([point("new-ticket", "b"), point("make-plan", "t")], "dashed", "promote", None),
        ([point("make-roadmap", "r"), point("make-plan", "l")], "solid", None, None),
        ([point("make-plan", "r"), point("implement-plan", "l")], "solid", None, None),
        ([point("implement-plan", "r"), point("deep-review", "l")], "solid", None, None),
        ([point("deep-review", "r"), point("ship-work", "l")], "solid", None, None),
        ([point("make-plan", "b"), point("plan-page", "t")], "dotted", "explain", None),
        ([point("implement-plan", "b", 40), point("save-learning", "t", -40)], "dashed", "lessons", None),
        ([point("find-bug", "r"), point("save-learning", "l")], "dashed", None, None),
        (
            [found_bug, (found_bug[0], detour), (ship[0], detour), ship],
            "dashed",
            "fix, then ship",
            (ship[0] - 10, detour - 6, "end"),
        ),
    ]


def text(x: float, y: float, content: str, fill: str, size: float = 11.5, extra: str = "") -> str:
    return f'<text x="{x:g}" y="{y:g}" font-family="{SANS}" font-size="{size}" fill="{fill}"{extra}>{content}</text>'


def path_data(points: list[tuple[float, float]], radius: float = 12) -> str:
    """Straight segments, with rounded corners where the path turns."""
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        return f"M{x1:g},{y1:g} L{x2:g},{y2:g}"
    data = f"M{points[0][0]:g},{points[0][1]:g}"
    for (px, py), (cx, cy), (nx, ny) in zip(points, points[1:], points[2:]):
        bx = cx - radius * ((cx > px) - (cx < px))
        by = cy - radius * ((cy > py) - (cy < py))
        ax = cx + radius * ((nx > cx) - (nx < cx))
        ay = cy + radius * ((ny > cy) - (ny < cy))
        data += f" L{bx:g},{by:g} Q{cx:g},{cy:g} {ax:g},{ay:g}"
    return data + f" L{points[-1][0]:g},{points[-1][1]:g}"


def trim(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Leave a small gap between the arrowhead and the node it points to."""
    (px, py), (x, y) = points[-2], points[-1]
    length = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
    return points[:-1] + [(x - 4 * (x - px) / length, y - 4 * (y - py) / length)]


def svg(theme: str) -> str:
    t = THEMES[theme]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
        'role="img" aria-label="Workflow: research-topic and new-ticket feed make-roadmap and make-plan; make-plan, '
        'implement-plan, deep-review and ship-work are the main flow; plan-page, find-bug and save-learning plug in.">',
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="{t["line"]}"/></marker></defs>',
    ]

    for label, first, last, colour in STAGES:
        x0, x1 = COL[first], COL[last] + W
        out.append(text(x0, 30, label, t[colour], 12, ' font-weight="700" letter-spacing="1.5"'))
        out.append(f'<line x1="{x0}" y1="40" x2="{x1}" y2="40" stroke="{t[colour]}" stroke-width="2" '
                   'stroke-linecap="round" opacity="0.6"/>')

    italic = ' font-style="italic"'
    for points, style, label, label_at in edges():
        width = 2 if style == "solid" else 1.5
        out.append(f'<path d="{path_data(trim(points))}" fill="none" stroke="{t["line"]}" stroke-width="{width}"'
                   f'{DASH[style]} marker-end="url(#arrow)"/>')
        if not label:
            continue
        if label_at:
            x, y, anchor = label_at
        else:
            (x1, y1), (x2, y2) = points[0], points[-1]
            x, y, anchor = (x1 + x2) / 2, (y1 + y2) / 2, "middle"
            if x1 == x2:
                x, y, anchor = x + 8, y + 4, "start"
            else:
                x, y, anchor = x + 16, y - 6, "start"
        out.append(text(x, y, label, t["muted"], extra=f' text-anchor="{anchor}"{italic}'))

    # Legend, in the free space above build, check and deliver.
    x0, y0 = COL[2] + 4, ROW["top"] + 22
    for i, (label, style) in enumerate([("main flow", "solid"), ("optional or side path", "dashed"),
                                        ("generated from", "dotted")]):
        y = y0 + 20 * i
        width = 2 if style == "solid" else 1.5
        out.append(f'<path d="M{x0},{y} L{x0 + 34},{y}" stroke="{t["line"]}" stroke-width="{width}"'
                   f'{DASH[style]} marker-end="url(#arrow)"/>')
        out.append(text(x0 + 46, y + 4, label, t["muted"], 12))
    x0 = COL[3] + 40
    for i, (label, dash) in enumerate([("core step", ""), ("optional step", ' stroke-dasharray="5 3"')]):
        y = y0 + 20 * i
        out.append(f'<rect x="{x0}" y="{y - 7}" width="34" height="14" rx="5" fill="none" stroke="{t["muted"]}" '
                   f'stroke-width="1.5"{dash}/>')
        out.append(text(x0 + 46, y + 4, label, t["muted"], 12))
    out.append(text(x0, y0 + 44, f'all share <tspan font-family="{MONO}">plans/</tspan>', t["muted"], 12))

    for name, (column, row, colour, subtitle, kind) in NODES.items():
        x, y, accent = COL[column], ROW[row], t[colour]
        fill, opacity, stroke, dash = {
            "core": (accent, 0.12, 2, ""),
            "optional": (accent, 0.06, 1.5, ' stroke-dasharray="6 4"'),
            "side": (t["bg"], 1, 1.25, ""),
        }[kind]
        # An opaque base first, so arrows never show through tinted nodes.
        out.append(f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="12" fill="{t["bg"]}"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="12" fill="{fill}" fill-opacity="{opacity}" '
                   f'stroke="{accent}" stroke-width="{stroke}"{dash}/>')
        out.append(f'<text x="{x + W / 2:g}" y="{y + 26}" text-anchor="middle" font-family="{MONO}" font-size="14" '
                   f'font-weight="700" fill="{t["text"]}">{name}</text>')
        out.append(text(x + W / 2, y + 45, subtitle, t["muted"], extra=' text-anchor="middle"'))

    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the files differ from what would be drawn")
    parser.add_argument("--out", type=Path, default=IMAGES)
    args = parser.parse_args(argv)

    outdated = []
    for theme in THEMES:
        target = args.out / f"workflow-{theme}.svg"
        content = svg(theme)
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != content:
                outdated.append(target)
        else:
            target.write_text(content, encoding="utf-8")
            print(f"wrote {target}")
    for target in outdated:
        print(f"outdated: {target}; run scripts/draw_workflow.py")
    return 1 if outdated else 0


if __name__ == "__main__":
    sys.exit(main())
