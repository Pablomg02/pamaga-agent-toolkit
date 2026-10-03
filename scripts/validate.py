#!/usr/bin/env python3
"""Validate the skills, commands, agents and evals of this toolkit.

Checks the rules in docs/CONVENTIONS.md so a broken skill never gets
installed: frontmatter, names, description limits, bundled files referenced
from SKILL.md, opencode command wrappers and eval files.

Usage:
    python3 scripts/validate.py          # check, exit 1 on errors
    python3 scripts/validate.py --fix    # also (re)write command wrappers

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
SKILL_MAX_LINES = 500
SKILL_KEYS = {"name", "description", "license", "compatibility", "metadata", "user-invocable"}
BUNDLED_DIRS = ("references", "scripts", "assets", "templates")
BUNDLED_REF_RE = re.compile(r"`((?:%s)/[^`\s]+)`" % "|".join(BUNDLED_DIRS))
# Another skill's file, through its folder placeholder: `<plans-convention>/scripts/plans.py`.
CROSS_REF_RE = re.compile(r"<([a-z0-9-]+)>/((?:%s)/[^`\s]+)" % "|".join(BUNDLED_DIRS))

WRAPPER_TEMPLATE = """---
description: {description}
---

Load and follow the `{name}` skill. $ARGUMENTS
"""


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.fixed: list[str] = []

    def error(self, where: Path | str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warning(self, where: Path | str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def split_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """Return (top-level scalar keys, body), or None without frontmatter.

    Only the flat subset used in this repository is supported. Nested keys
    (indented lines, e.g. under `metadata:`) are skipped.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for end, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
    else:
        return None
    data: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        if ":" not in line:
            data.setdefault("__invalid__", line)
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data, "\n".join(lines[end + 1 :])


def plain_scalar_problem(value: str) -> str | None:
    """Why a value is not a safe single-line YAML plain scalar, if it is not."""
    if value[:1] in "\"'":
        return None  # quoted: the YAML parser handles it
    if value[:1] and value[0] in "!&*>|%@`[]{},#" or value.startswith(("- ", "? ", ": ")):
        return f"starts with {value[0]!r}, a YAML indicator; quote the value"
    if ": " in value or value.endswith(":"):
        return "contains ': ' which YAML reads as a mapping; quote the value or rephrase"
    if " #" in value:
        return "contains ' #' which YAML reads as a comment; quote the value or rephrase"
    return None


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def check_skill(skill_dir: Path, report: Report) -> tuple[str | None, bool]:
    """Validate one skill folder; return (description if usable, user-invocable)."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        report.error(skill_dir, "missing SKILL.md")
        return None, True
    text = skill_md.read_text(encoding="utf-8")
    parsed = split_frontmatter(text)
    if parsed is None:
        report.error(skill_md, "missing or unterminated frontmatter")
        return None, True
    meta, body = parsed

    if "__invalid__" in meta:
        report.error(skill_md, f"unparseable frontmatter line: {meta['__invalid__']!r}")
    for key in sorted(set(meta) - SKILL_KEYS - {"__invalid__"}):
        report.error(skill_md, f"frontmatter key {key!r} is not portable; allowed: {sorted(SKILL_KEYS)}")

    invocable = unquote(meta.get("user-invocable", "true"))
    if invocable not in ("true", "false"):
        report.error(skill_md, f"user-invocable must be true or false, not {invocable!r}")

    name = unquote(meta.get("name", ""))
    if not name:
        report.error(skill_md, "missing name")
    else:
        if not NAME_RE.match(name) or len(name) > NAME_MAX:
            report.error(skill_md, f"name {name!r} must match {NAME_RE.pattern} and be <= {NAME_MAX} chars")
        if name != skill_dir.name:
            report.error(skill_md, f"name {name!r} does not match folder {skill_dir.name!r}")

    raw_description = meta.get("description", "")
    description = unquote(raw_description)
    if not description:
        report.error(skill_md, "missing description")
    else:
        if len(description) > DESCRIPTION_MAX:
            report.error(skill_md, f"description is {len(description)} chars, max {DESCRIPTION_MAX}")
        problem = plain_scalar_problem(raw_description)
        if problem:
            report.error(skill_md, f"description {problem}")

    line_count = len(text.splitlines())
    if line_count > SKILL_MAX_LINES:
        report.warning(skill_md, f"{line_count} lines; move detail to references/ (target <= {SKILL_MAX_LINES})")
    if not body.strip():
        report.error(skill_md, "empty body")

    referenced = set()
    for ref in BUNDLED_REF_RE.findall(body):
        if "<" in ref or "{" in ref or "*" in ref:
            continue  # a pattern such as references/themes/<theme>.md
        referenced.add(ref)
        if not (skill_dir / ref).exists():
            report.error(skill_md, f"references {ref}, which does not exist")

    for other, ref in CROSS_REF_RE.findall(body):
        if "<" in ref or "{" in ref or "*" in ref:
            continue
        if not (skill_dir.parent / other / ref).exists():
            report.error(skill_md, f"references <{other}>/{ref}, which does not exist")

    for folder in BUNDLED_DIRS:
        for path in sorted((skill_dir / folder).rglob("*")) if (skill_dir / folder).is_dir() else []:
            if path.is_file() and not path.name.startswith(".") and "__pycache__" not in path.parts:
                relative = path.relative_to(skill_dir).as_posix()
                if relative not in referenced:
                    report.warning(path, "bundled file not referenced from SKILL.md")

    return description or None, invocable != "false"


def check_wrapper(repo: Path, name: str, description: str, fix: bool, report: Report) -> None:
    wrapper = repo / "commands" / f"{name}.md"
    expected = WRAPPER_TEMPLATE.format(name=name, description=description)
    if wrapper.is_file() and wrapper.read_text(encoding="utf-8") == expected:
        return
    if fix:
        wrapper.parent.mkdir(exist_ok=True)
        wrapper.write_text(expected, encoding="utf-8")
        report.fixed.append(str(wrapper))
    elif wrapper.is_file():
        report.error(wrapper, "out of sync with the skill; run scripts/validate.py --fix")
    else:
        report.error(wrapper, f"missing opencode wrapper for skill {name!r}; run scripts/validate.py --fix")


def check_no_wrapper(repo: Path, name: str, fix: bool, report: Report) -> None:
    """A skill with user-invocable: false is loaded by other skills, not typed."""
    wrapper = repo / "commands" / f"{name}.md"
    if not wrapper.is_file():
        return
    if fix:
        wrapper.unlink()
        report.fixed.append(f"{wrapper} (removed)")
    else:
        report.error(wrapper, f"skill {name!r} is not user-invocable and must not have a wrapper; run scripts/validate.py --fix")


def check_commands(repo: Path, skill_names: set[str], report: Report) -> None:
    for command in sorted((repo / "commands").glob("*.md")):
        parsed = split_frontmatter(command.read_text(encoding="utf-8"))
        if parsed is None or not parsed[0].get("description"):
            report.error(command, "commands need frontmatter with a description")
            continue
        if NAME_RE.match(command.stem) is None:
            report.error(command, f"file name must match {NAME_RE.pattern}")
        body = parsed[1]
        loads = re.search(r"Load and follow the `([^`]+)` skill", body)
        if loads and loads.group(1) not in skill_names:
            report.error(command, f"wraps skill {loads.group(1)!r}, which does not exist")


def check_agents(repo: Path, report: Report) -> None:
    for agent in sorted((repo / "agents").glob("*.md")):
        parsed = split_frontmatter(agent.read_text(encoding="utf-8"))
        if parsed is None:
            report.error(agent, "missing frontmatter")
            continue
        meta, body = parsed
        if unquote(meta.get("name", "")) != agent.stem:
            report.error(agent, "name must be present and equal the file name (Claude Code skips the file otherwise)")
        if not meta.get("description"):
            report.error(agent, "missing description")
        for key in ("tools", "permissionMode"):
            if key in meta:
                report.warning(agent, f"{key!r} is Claude-only; see docs/CONVENTIONS.md")
        if not body.strip():
            report.error(agent, "empty prompt")


def check_evals(repo: Path, skill_names: set[str], report: Report) -> None:
    evals_dir = repo / "evals"
    for name in sorted(skill_names):
        path = evals_dir / f"{name}.json"
        if not path.is_file():
            report.error(path, f"missing eval file for skill {name!r}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            report.error(path, f"invalid JSON: {error}")
            continue
        if not isinstance(data, dict):
            report.error(path, "top level must be an object")
            continue
        if data.get("skill_name") != name:
            report.error(path, f"skill_name must be {name!r}")

        evals = data.get("evals")
        if not isinstance(evals, list) or not evals:
            report.error(path, "evals must be a non-empty list")
        else:
            ids = []
            for index, case in enumerate(evals):
                where = f"{path} evals[{index}]"
                if not isinstance(case, dict):
                    report.error(where, "must be an object")
                    continue
                ids.append(case.get("id"))
                if not isinstance(case.get("id"), int):
                    report.error(where, "id must be an integer")
                for key in ("prompt", "expected_output"):
                    if not isinstance(case.get(key), str) or not case.get(key).strip():
                        report.error(where, f"{key} must be a non-empty string")
                expectations = case.get("expectations")
                if not isinstance(expectations, list) or not expectations or not all(
                    isinstance(item, str) and item.strip() for item in expectations
                ):
                    report.error(where, "expectations must be a non-empty list of strings")
                files = case.get("files", [])
                if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
                    report.error(where, "files must be a list of strings")
            if len(ids) != len(set(map(str, ids))):
                report.error(path, "eval ids must be unique")

        triggers = data.get("trigger_evals")
        if not isinstance(triggers, list) or not triggers:
            report.error(path, "trigger_evals must be a non-empty list")
            continue
        kinds = set()
        for index, case in enumerate(triggers):
            where = f"{path} trigger_evals[{index}]"
            if (
                not isinstance(case, dict)
                or not isinstance(case.get("query"), str)
                or not case["query"].strip()
                or not isinstance(case.get("should_trigger"), bool)
            ):
                report.error(where, "needs a non-empty 'query' string and a boolean 'should_trigger'")
                continue
            kinds.add(case["should_trigger"])
        if kinds and kinds != {True, False}:
            report.error(path, "trigger_evals need both should_trigger true and false cases")

    for path in sorted(evals_dir.glob("*.json")) if evals_dir.is_dir() else []:
        if path.stem not in skill_names:
            report.error(path, f"eval file for unknown skill {path.stem!r}")


def validate(repo: Path, fix: bool = False) -> Report:
    report = Report()
    skills_dir = repo / "skills"
    skill_names: set[str] = set()
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []:
        description, invocable = check_skill(skill_dir, report)
        skill_names.add(skill_dir.name)
        if not invocable:
            check_no_wrapper(repo, skill_dir.name, fix, report)
        elif description:
            check_wrapper(repo, skill_dir.name, description, fix, report)
    check_commands(repo, skill_names, report)
    check_agents(repo, report)
    check_evals(repo, skill_names, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fix", action="store_true", help="write missing or outdated command wrappers")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    report = validate(args.repo, fix=args.fix)
    for path in report.fixed:
        print(f"fixed: {path}")
    for message in report.errors:
        print(f"error: {message}")
    for message in report.warnings:
        print(f"warning: {message}")
    if report.errors:
        print(f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")
        return 1
    print(f"ok: {len(report.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
