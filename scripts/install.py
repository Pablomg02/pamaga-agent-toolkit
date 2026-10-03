#!/usr/bin/env python3
"""Entry point for the toolkit installer.

With an interactive terminal it runs the TUI; otherwise it behaves like the
non-interactive CLI (`--yes`, `--status`, `--uninstall`, `--version`). This
folder is put on `sys.path` so the `installer` package next to it is
importable from any working directory, and bytecode is kept out of the
repository (some skill folders are symlinked into harnesses).

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from installer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
