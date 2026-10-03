"""Where each supported harness keeps its skills, agents and commands.

The installer never guesses a path: every harness comes from
`HARNESS_SPECS`, a module-level registry of small specs, so adding a
harness is one entry here plus a line in docs/INSTALL.md.

Bases are always resolved from the `env` mapping the caller passes (or from
`os.environ` when it passes none), never from the real home by accident:
tests redirect the whole installation with a fake mapping.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DIR_NAMES = {"skill": "skills", "agent": "agents", "command": "commands"}


@dataclass(frozen=True)
class Harness:
    """One agent harness and the base directory it reads from."""

    id: str
    label: str
    base: Path
    binary: str
    supports_commands: bool
    restart_hint: str
    skills_from: str | None = None  # id of a harness whose skills dir this one also reads

    def dir_for(self, kind: str) -> Path:
        """Directory holding items of `kind`: "skill", "agent" or "command"."""
        try:
            sub = DIR_NAMES[kind]
        except KeyError:
            raise ValueError(f"unknown item kind: {kind!r}") from None
        return self.base / sub

    def detected(self) -> bool:
        """True when the base exists or the harness executable is on PATH."""
        return self.base.exists() or shutil.which(self.binary) is not None


@dataclass(frozen=True)
class HarnessSpec:
    """Registry entry: identity plus the dirs a harness uses under each root."""

    id: str
    label: str
    binary: str
    supports_commands: bool
    restart_hint: str
    user_root: str  # "xdg" (XDG_CONFIG_HOME, fallback ~/.config) or "home"
    user_dir: str
    project_dir: str
    skills_from: str | None = None


HARNESS_SPECS: tuple[HarnessSpec, ...] = (
    HarnessSpec(
        id="opencode",
        label="opencode",
        binary="opencode",
        supports_commands=True,
        restart_hint="Restart opencode to pick up the changes.",
        user_root="xdg",
        user_dir="opencode",
        project_dir=".opencode",
        skills_from="claude",
    ),
    HarnessSpec(
        id="claude",
        label="Claude Code",
        binary="claude",
        supports_commands=False,
        restart_hint="Restart Claude Code to pick up the changes.",
        user_root="home",
        user_dir=".claude",
        project_dir=".claude",
    ),
)


def all_harnesses(
    scope: str = "user",
    project: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Harness]:
    """Every known harness with its base directory resolved for `scope`.

    User scope reads HOME and XDG_CONFIG_HOME from `env` (default
    `os.environ`), falling back to USERPROFILE and `~/.config`; project
    scope resolves under `project`, defaulting to the current directory.
    """
    env = os.environ if env is None else env
    if scope == "user":
        home = _home(env)
        xdg = env.get("XDG_CONFIG_HOME")
        roots = {"home": home, "xdg": Path(xdg) if xdg else home / ".config"}
        return [_build(spec, roots[spec.user_root] / spec.user_dir) for spec in HARNESS_SPECS]
    if scope == "project":
        root = Path(project) if project is not None else Path.cwd()
        return [_build(spec, root / spec.project_dir) for spec in HARNESS_SPECS]
    raise ValueError(f"unknown scope: {scope!r} (expected 'user' or 'project')")


def _home(env: Mapping[str, str]) -> Path:
    value = env.get("HOME") or env.get("USERPROFILE")
    return Path(value) if value else Path.home()


def _build(spec: HarnessSpec, base: Path) -> Harness:
    return Harness(
        id=spec.id,
        label=spec.label,
        base=base,
        binary=spec.binary,
        supports_commands=spec.supports_commands,
        restart_hint=spec.restart_hint,
        skills_from=spec.skills_from,
    )
