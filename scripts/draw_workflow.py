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

SCRIPTS = Path(__file__).resolve().parent
IMAGES = SCRIPTS.parent / "images"

# The dark theme is the installer's palette, so the README diagram and the TUI
# share one source of colours.
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from installer.tui.style import THEME  # noqa: E402

THEMES = {
    "light": dict(text="#1f2328", muted="#59636e", line="#8c959f", bg="#ffffff",
                  think="#2563eb", build="#059669", check="#c2410c", deliver="#7c3aed", keep="#db2777"),
    "dark": dict(THEME),
}

SANS = "ui-sans-serif, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace"
LEFT, SPAN = 40, 990                    # drawing area: x from LEFT to LEFT + SPAN
WIDTH = LEFT * 2 + SPAN

# Two rows: the main flow, and the skills you call at any point.
ROWS = {
    "main": dict(y=64, w=210, h=64, count=4),
    "any": dict(y=228, w=150, h=56, count=6),
}
HEIGHT = ROWS["any"]["y"] + ROWS["any"]["h"] + 12

# name: column, row, colour (stage), subtitle, kind (core | side).
# The installer reads the colour as the skill's stage, the subtitle as its
# tagline, and the order of this dict (the flow of a change) as its menu
# order within a stage, so keep the subtitles short and the order natural.
NODES = {
    "research-topic": (0, "any", "think", "answers with evidence", "side"),
    "make-roadmap": (1, "any", "think", "weeks-long goals", "side"),
    "make-plan": (0, "main", "think", "precise plan.md", "core"),
    "new-ticket": (2, "any", "think", "capture for later", "side"),
    "plan-page": (3, "any", "think", "HTML explainer", "side"),
    "implement-plan": (1, "main", "build", "code + tests, uncommitted", "core"),
    "find-bug": (4, "any", "build", "root cause + test", "side"),
    "deep-review": (2, "main", "check", "findings, then fixes", "core"),
    "ship-work": (3, "main", "deliver", "commit · push · PR", "core"),
    "save-learning": (5, "any", "keep", "docs/learnings/", "side"),
}

# Who does each main step (see docs/PHILOSOPHY.md).
MODEL = {
    "make-plan": "best model",
    "implement-plan": "cheap model",
    "deep-review": "best model",
    "ship-work": "when you approve",
}


def box(name: str) -> tuple[float, float, float, float]:
    """x, y, width, height of a node, its row spread evenly over the span."""
    column, row, *_ = NODES[name]
    r = ROWS[row]
    gap = (SPAN - r["count"] * r["w"]) / (r["count"] - 1)
    return LEFT + column * (r["w"] + gap), r["y"], r["w"], r["h"]


def text(x: float, y: float, content: str, fill: str, size: float = 11.5, extra: str = "") -> str:
    return f'<text x="{x:g}" y="{y:g}" font-family="{SANS}" font-size="{size}" fill="{fill}"{extra}>{content}</text>'


def svg(theme: str) -> str:
    t = THEMES[theme]
    arrow = ' marker-end="url(#arrow)"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
        'role="img" aria-label="Main flow: make-plan with the best model, implement-plan with a cheap model, '
        'deep-review with the best model, then ship-work; large fixes go back to a plan. At any point: '
        'research-topic, make-roadmap, new-ticket, plan-page, find-bug, save-learning.">',
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="{t["line"]}"/></marker></defs>',
    ]

    # Main flow: arrows between consecutive steps.
    main = [name for name in NODES if NODES[name][1] == "main"]
    for a, b in zip(main, main[1:]):
        ax, ay, aw, ah = box(a)
        bx, *_ = box(b)
        y = ay + ah / 2
        out.append(f'<path d="M{ax + aw + 6:g},{y:g} L{bx - 8:g},{y:g}" stroke="{t["line"]}" stroke-width="2"{arrow}/>')

    # Large fixes found by the review go back to a plan.
    rx, ry, rw, _ = box("deep-review")
    px, _, pw, _ = box("make-plan")
    x1, x2, top, r = rx + rw / 2, px + pw / 2, 26, 12
    out.append(f'<path d="M{x1:g},{ry - 4:g} L{x1:g},{top + r} Q{x1:g},{top} {x1 - r:g},{top} '
               f'L{x2 + r:g},{top} Q{x2:g},{top} {x2:g},{top + r} L{x2:g},{ry - 6:g}" fill="none" '
               f'stroke="{t["line"]}" stroke-width="1.5" stroke-dasharray="5 4"{arrow}/>')
    out.append(text((x1 + x2) / 2, top - 7, "large fixes become a new plan", t["muted"],
                    extra=' text-anchor="middle" font-style="italic"'))

    # Section label for the second row.
    label_y = ROWS["any"]["y"] - 22
    out.append(text(LEFT, label_y, "AT ANY POINT", t["muted"], 12, ' font-weight="700" letter-spacing="1.5"'))
    out.append(text(LEFT + SPAN, label_y, f'everything is Markdown in <tspan font-family="{MONO}">plans/</tspan> '
                    f'and <tspan font-family="{MONO}">docs/</tspan>', t["muted"], 12, ' text-anchor="end"'))
    out.append(f'<line x1="{LEFT}" y1="{label_y + 9}" x2="{LEFT + SPAN}" y2="{label_y + 9}" stroke="{t["line"]}" '
               'stroke-width="1" opacity="0.5"/>')

    for name, (_, row, colour, subtitle, kind) in NODES.items():
        x, y, w, h = box(name)
        accent = t[colour]
        core = kind == "core"
        out.append(f'<rect x="{x:g}" y="{y}" width="{w}" height="{h}" rx="12" fill="{t["bg"]}"/>')
        out.append(f'<rect x="{x:g}" y="{y}" width="{w}" height="{h}" rx="12" fill="{accent}" '
                   f'fill-opacity="{0.12 if core else 0}" stroke="{accent}" stroke-width="{2 if core else 1.25}"/>')
        out.append(f'<text x="{x + w / 2:g}" y="{y + h / 2 - 3:g}" text-anchor="middle" font-family="{MONO}" '
                   f'font-size="{15 if core else 13.5}" font-weight="700" fill="{t["text"]}">{name}</text>')
        out.append(text(x + w / 2, y + h / 2 + 15, subtitle, t["muted"], extra=' text-anchor="middle"'))
        if name in MODEL:
            out.append(text(x + w / 2, y + h + 20, MODEL[name], accent, 12,
                            ' text-anchor="middle" font-weight="600"'))

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
