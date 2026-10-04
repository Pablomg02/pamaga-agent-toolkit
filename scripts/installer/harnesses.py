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
_OFF_VALUES = {"false", "0", "no", "off"}


@dataclass(frozen=True)
class CompatSwitch:
    """A harness setting that can stop it reading another harness's skills dir."""

    env: str      # environment variable; set and false-like turns it off
    config: str   # config file, relative to the harness's user base
    table: str    # TOML table holding the key, e.g. "compat.claude"
    key: str      # boolean key in that table, e.g. "skills"


@dataclass(frozen=True)
class Harness:
    """One agent harness and the base directory it reads from."""

    id: str
    label: str
    base: Path
    binary: str
    supports_commands: bool
    restart_hint: str
    # ids of harnesses whose skills dir this one also reads at this scope
    skills_from: tuple[str, ...] = ()
    # (provider id, reason) for providers dropped because a setting turned them off
    skills_from_disabled: tuple[tuple[str, str], ...] = ()
    # False when the harness expects another agent layout than agents/<name>.md
    supports_agents: bool = True

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
    # Environment variable that, when set, replaces the whole user base.
    user_env: str | None = None
    skills_from: tuple[str, ...] = ()  # ids whose skills dir the harness reads (user scope)
    # Like skills_from but for project scope; None means "same as skills_from".
    project_skills_from: tuple[str, ...] | None = None
    supports_agents: bool = True
    # (provider id, switch) for providers a setting can stop this harness reading
    skills_from_switches: tuple[tuple[str, CompatSwitch], ...] = ()


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
        # opencode also reads Claude's skills dir at both scopes and the
        # Antigravity .agents dir in a project: when both are selected the
        # skills go there only, never duplicated in .opencode/skills.
        skills_from=("claude",),
        project_skills_from=("claude", "antigravity"),
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
    HarnessSpec(
        id="antigravity",
        label="Antigravity CLI",
        binary="agy",
        supports_commands=False,
        restart_hint="Restart Antigravity CLI to pick up the changes.",
        # Skills, subagents and hooks share this global root across the
        # Antigravity surfaces; project scope uses the universal .agents dir.
        user_root="home",
        user_dir=".gemini/config",
        project_dir=".agents",
        # Its agents are agents/<name>/agent.md, not agents/<name>.md.
        supports_agents=False,
    ),
    HarnessSpec(
        id="grok",
        label="Grok CLI",
        binary="grok",
        supports_commands=False,
        restart_hint="Grok CLI reloads skills on its own; restart it if a change does not show up.",
        user_root="home",
        user_dir=".grok",
        project_dir=".grok",
        user_env="GROK_HOME",
        # Grok reads Claude's skills dir (and, in a project, the Antigravity
        # .agents dir) unless Claude compatibility for skills is off.
        # See docs/INSTALL.md.
        skills_from=("claude",),
        project_skills_from=("claude", "antigravity"),
        skills_from_switches=(
            ("claude", CompatSwitch(
                env="GROK_CLAUDE_SKILLS_ENABLED",
                config="config.toml",
                table="compat.claude",
                key="skills",
            )),
        ),
    ),
)


def all_harnesses(
    scope: str = "user",
    project: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Harness]:
    """Every known harness with its base directory resolved for `scope`.

    User scope reads HOME and XDG_CONFIG_HOME from `env` (default
    `os.environ`), falling back to USERPROFILE and `~/.config`; a harness
    with a `user_env` (Grok's GROK_HOME) uses that variable instead when it
    is set. Project scope resolves under `project`, defaulting to the
    current directory.
    """
    env = os.environ if env is None else env
    home = _home(env)
    xdg = env.get("XDG_CONFIG_HOME")
    roots = {"home": home, "xdg": Path(xdg) if xdg else home / ".config"}
    # The user base also holds a harness's config, read at both scopes.
    user_bases = {spec.id: _user_base(spec, roots, env) for spec in HARNESS_SPECS}
    if scope == "user":
        return [
            _build(
                spec,
                user_bases[spec.id],
                *_reachable(spec, spec.skills_from, env, user_bases[spec.id]),
            )
            for spec in HARNESS_SPECS
        ]
    if scope == "project":
        root = Path(project) if project is not None else Path.cwd()
        return [
            _build(
                spec,
                root / spec.project_dir,
                *_reachable(
                    spec,
                    spec.skills_from if spec.project_skills_from is None else spec.project_skills_from,
                    env,
                    user_bases[spec.id],
                ),
            )
            for spec in HARNESS_SPECS
        ]
    raise ValueError(f"unknown scope: {scope!r} (expected 'user' or 'project')")


def _home(env: Mapping[str, str]) -> Path:
    value = env.get("HOME") or env.get("USERPROFILE")
    return Path(value) if value else Path.home()


def _user_base(spec: HarnessSpec, roots: Mapping[str, Path], env: Mapping[str, str]) -> Path:
    """User-scope base of `spec`: its own env override when set, else root plus dir."""
    override = env.get(spec.user_env) if spec.user_env else None
    return Path(override) if override else roots[spec.user_root] / spec.user_dir


def _reachable(
    spec: HarnessSpec,
    providers: tuple[str, ...],
    env: Mapping[str, str],
    user_base: Path,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Split `providers` into those still read and those a switch turned off.

    Order of each tuple follows `providers`. A provider with no switch, or
    whose switch is on, stays reachable.
    """
    switches = {provider: switch for provider, switch in spec.skills_from_switches}
    kept: list[str] = []
    disabled: list[tuple[str, str]] = []
    for provider in providers:
        switch = switches.get(provider)
        reason = None if switch is None else _switch_off_reason(switch, env, user_base)
        if reason is None:
            kept.append(provider)
        else:
            disabled.append((provider, reason))
    return tuple(kept), tuple(disabled)


def _switch_off_reason(switch: CompatSwitch, env: Mapping[str, str], user_base: Path) -> str | None:
    """Why `switch` is off, or None when the harness still reads that dir.

    A non-empty environment variable decides alone. Otherwise a `false` value
    in the config file turns it off. A missing, unreadable or silent file
    leaves it on.
    """
    raw = env.get(switch.env)
    if raw:
        if raw.strip().lower() in _OFF_VALUES:
            return f"{switch.env}={raw}"
        return None
    path = user_base / switch.config
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if _toml_bool(text, switch.table, switch.key) is False:
        return f"{switch.table}.{switch.key} = false in {path}"
    return None


def _dotted(text: str) -> tuple[str, ...]:
    """Split a TOML dotted name, ignoring spaces around the dots."""
    return tuple(part.strip() for part in text.split("."))


def _toml_bool(text: str, table: str, key: str) -> bool | None:
    """First `true` or `false` written for `table.key`, else None.

    Understands `key = <bool>` under `[table]`, a dotted key under a parent
    table, and the full dotted key before any table. `#` comments are
    stripped. Quoted keys and inline tables are not a match.
    """
    target = _dotted(f"{table}.{key}")
    current: tuple[str, ...] = ()
    seen_table = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            seen_table = True
            current = _dotted(line[1:-1].strip())
            continue
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        parts = _dotted(left.strip())
        full = parts if not seen_table else current + parts
        if full != target:
            continue
        value = right.strip()
        if value == "true":
            return True
        if value == "false":
            return False
    return None


def _build(
    spec: HarnessSpec,
    base: Path,
    skills_from: tuple[str, ...],
    skills_from_disabled: tuple[tuple[str, str], ...],
) -> Harness:
    return Harness(
        id=spec.id,
        label=spec.label,
        base=base,
        binary=spec.binary,
        supports_commands=spec.supports_commands,
        restart_hint=spec.restart_hint,
        skills_from=skills_from,
        skills_from_disabled=skills_from_disabled,
        supports_agents=spec.supports_agents,
    )
