"""Installer terminal UI: terminal I/O, style, widgets, logo and the app.

The package is imported lazily by the CLI, so import it only when the TUI is
actually going to run: `tui/terminal.py` is the only module that touches the
real terminal.
"""

from __future__ import annotations
