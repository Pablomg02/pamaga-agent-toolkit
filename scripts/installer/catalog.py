"""Discover the toolkit's skills, commands and agents with metadata and hashes.

The catalog is the installer's view of the repository: what can be
installed, how skills are grouped, what each item requires, which files it
contains and a content hash to compare a source folder with an installed
copy.

Metadata comes from frontmatter (parsed with the repository's own
``scripts/validate.py``), stage and tagline come from ``NODES`` in
``scripts/draw_workflow.py`` so the TUI never disagrees with the README
diagram, and dependencies are detected from the prose rules in
docs/CONVENTIONS.md.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

IGNORED_NAMES = {"__pycache__", ".DS_Store", ".gitkeep"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}

STAGE_ORDER = ("think", "build", "check", "deliver", "keep", "support")

_WHITESPACE_RE = re.compile(r"\s+")

# A module cache so load_catalog() does not exec the repository's scripts
# again on every call (the TUI reloads the catalog after a pull).
_MODULES: dict[tuple[str, str], ModuleType] = {}


@dataclass(frozen=True)
class Item:
    """One installable thing: a skill folder, an agent file or a command file."""

    kind: str                 # "skill" | "agent" | "command"
    name: str                 # folder or file stem
    source: Path              # absolute: skills/<n>/ dir, agents/<n>.md, commands/<n>.md
    description: str          # frontmatter description ("" if missing)
    user_invocable: bool      # False when frontmatter says user-invocable: false
    stage: str                # think|build|check|deliver|keep from NODES; "support" otherwise
    tagline: str              # NODES subtitle, or "" (commands/agents: "")
    requires: tuple[str, ...] # skill names, sorted, never itself
    files: tuple[str, ...]    # posix paths relative to source (file items: (name,)), sorted
    content_hash: str         # "sha256:<hex>" over files, see content_hash()

    @property
    def key(self) -> str:
        return f"{self.kind}/{self.name}"

    @property
    def is_dir(self) -> bool:
        return self.kind == "skill"


@dataclass(frozen=True)
class Catalog:
    """Everything installable in one repository clone."""

    repo: Path
    skills: tuple[Item, ...]    # sorted by (STAGE_ORDER index, NODES order, name)
    agents: tuple[Item, ...]    # sorted by name
    commands: tuple[Item, ...]  # sorted by name

    def get(self, kind: str, name: str) -> Item | None:
        for item in self._for_kind(kind):
            if item.name == name:
                return item
        return None

    def command_for(self, skill: str) -> Item | None:
        return self.get("command", skill)

    def required_closure(self, skills: set[str]) -> set[str]:
        """The input skills plus everything they transitively require."""
        closure = set(skills)
        pending = list(skills)
        while pending:
            item = self.get("skill", pending.pop())
            if item is None:
                continue
            for required in item.requires:
                if required not in closure:
                    closure.add(required)
                    pending.append(required)
        return closure

    def dependents(self, skill: str) -> tuple[str, ...]:
        """Names of the skills that require ``skill``, sorted."""
        return tuple(sorted(item.name for item in self.skills if skill in item.requires))

    def _for_kind(self, kind: str) -> tuple[Item, ...]:
        if kind == "skill":
            return self.skills
        if kind == "agent":
            return self.agents
        if kind == "command":
            return self.commands
        return ()


def list_files(path: Path) -> list[str]:
    """Files under ``path`` as sorted posix relative paths.

    Skips path components in IGNORED_NAMES and files with an ignored suffix
    (``__pycache__/``, ``.pyc``, ``.DS_Store``...) and never descends into
    symlinked directories. A file path yields ``[name]``.
    """
    path = Path(path)
    if path.is_file():
        if path.name in IGNORED_NAMES or path.suffix in IGNORED_SUFFIXES:
            return []
        return [path.name]
    if not path.is_dir():
        return []
    found: list[str] = []
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in IGNORED_NAMES)
        for name in sorted(files):
            if name in IGNORED_NAMES or Path(name).suffix in IGNORED_SUFFIXES:
                continue
            relative = os.path.relpath(os.path.join(root, name), path)
            found.append(Path(relative).as_posix())
    return sorted(found)


def content_hash(path: Path) -> str:
    """``"sha256:<hex>"`` over the names and bytes of every file under path.

    The same digest is produced for a source folder and for a copy of it,
    so an installed copy can be compared with the repository.
    """
    path = Path(path)
    digest = hashlib.sha256()
    for relative in list_files(path):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        file_path = path / relative if path.is_dir() else path
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def find_requires(skill_md_text: str, known: set[str], self_name: str) -> tuple[str, ...]:
    """Skill names a SKILL.md depends on, sorted.

    A known name ``X`` is a dependency when the text has the folder
    placeholder ``<X>`` or says "load [and follow] the `X` skill"
    (case-insensitive). Mentions such as "generated by the `X` skill" do
    not count, nor does the skill itself. Runs of whitespace are collapsed
    first, because some skills split the sentence across a line break.
    """
    text = _WHITESPACE_RE.sub(" ", skill_md_text)
    required = []
    for name in known:
        if name == self_name:
            continue
        phrase = re.compile(r"load (?:and follow )?the `%s` skill" % re.escape(name), re.IGNORECASE)
        if f"<{name}>" in text or phrase.search(text):
            required.append(name)
    return tuple(sorted(required))


def load_catalog(repo: Path) -> Catalog:
    """Read the whole repository: skills, agents and command wrappers."""
    repo = Path(repo).resolve()
    # Avoid __pycache__ next to the repository's scripts, like the tests do.
    sys.dont_write_bytecode = True
    validate = _repo_module(repo, "validate.py")
    draw = _repo_module(repo, "draw_workflow.py")
    nodes = draw.NODES

    skill_dirs = []
    skills_root = repo / "skills"
    if skills_root.is_dir():
        skill_dirs = sorted(
            path for path in skills_root.iterdir()
            if path.is_dir() and path.name not in IGNORED_NAMES
        )

    texts: dict[str, str] = {}
    for folder in skill_dirs:
        skill_md = folder / "SKILL.md"
        texts[folder.name] = skill_md.read_text(encoding="utf-8") if skill_md.is_file() else ""

    known = set(texts)
    skills = []
    for folder in skill_dirs:
        meta = _frontmatter(validate, texts[folder.name])
        node = nodes.get(folder.name)
        skills.append(
            Item(
                kind="skill",
                name=folder.name,
                source=folder,
                description=validate.unquote(meta.get("description", "")),
                user_invocable=validate.unquote(meta.get("user-invocable", "true")) != "false",
                stage=node[2] if node else "support",
                tagline=node[3] if node else "",
                requires=find_requires(texts[folder.name], known, folder.name),
                files=tuple(list_files(folder)),
                content_hash=content_hash(folder),
            )
        )

    flow = list(nodes)

    def skill_sort_key(item: Item) -> tuple[int, int, str]:
        position = flow.index(item.name) if item.name in nodes else len(flow)
        return (STAGE_ORDER.index(item.stage), position, item.name)

    skills.sort(key=skill_sort_key)

    agents = []
    agents_root = repo / "agents"
    if agents_root.is_dir():
        for path in sorted(agents_root.glob("*.md")):
            meta = _frontmatter(validate, path.read_text(encoding="utf-8"))
            agents.append(
                Item(
                    kind="agent",
                    name=path.stem,
                    source=path,
                    description=validate.unquote(meta.get("description", "")),
                    user_invocable=True,
                    stage="support",
                    tagline="",
                    requires=(),
                    files=tuple(list_files(path)),
                    content_hash=content_hash(path),
                )
            )

    commands = []
    commands_root = repo / "commands"
    if commands_root.is_dir():
        for path in sorted(commands_root.glob("*.md")):
            meta = _frontmatter(validate, path.read_text(encoding="utf-8"))
            commands.append(
                Item(
                    kind="command",
                    name=path.stem,
                    source=path,
                    description=validate.unquote(meta.get("description", "")),
                    user_invocable=True,
                    stage="support",
                    tagline="",
                    requires=(),
                    files=tuple(list_files(path)),
                    content_hash=content_hash(path),
                )
            )

    return Catalog(repo=repo, skills=tuple(skills), agents=tuple(agents), commands=tuple(commands))


def _frontmatter(validate: ModuleType, text: str) -> dict[str, str]:
    """Top-level frontmatter keys, or {} when there is no frontmatter."""
    parsed = validate.split_frontmatter(text)
    return parsed[0] if parsed is not None else {}


def _repo_module(repo: Path, filename: str) -> ModuleType:
    """Load one of the repository's own scripts through importlib.util."""
    key = (os.fspath(repo), filename)
    module = _MODULES.get(key)
    if module is not None:
        return module
    path = repo / "scripts" / filename
    spec = importlib.util.spec_from_file_location(f"pamaga_installer_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULES[key] = module
    return module
