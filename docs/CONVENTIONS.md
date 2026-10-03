# Conventions

How skills, commands and agents are written in this repository so the same
files work in opencode and Claude Code.

## Skills

- One folder per skill: `skills/<name>/SKILL.md`. `<name>` is lowercase
  hyphen-separated, up to 64 characters, and matches the folder name.
- Names are descriptive and must not collide with commands or agents built
  into the harnesses (Claude Code ships `/code-review`, `/review`, `/plan`,
  `/init`, `/simplify`...; opencode ships the `plan` and `build` agents).
  Prefer `verb-noun`: `make-plan`, `deep-review`.
- Frontmatter keeps the portable minimum: `name` and `description`. The
  description covers both what the skill does and when to use it, front-loading
  the words the user is likely to type.
- Body: plain Markdown, model-agnostic and tool-agnostic ("run the tests", not
  "use the Bash tool"), so it works with any model or harness.
- Skills are model-invocable: the agent loads them on its own when the
  description matches. There is no manual gating.
- Keep `SKILL.md` under 500 lines. Detail that is only needed at one step
  (subagent briefs, checklists, long examples) goes in `references/` and is
  linked from the step that needs it.
- Bundled files live inside the skill folder in `references/`, `scripts/`,
  `templates/` or `assets/`, and are referenced from `SKILL.md` relative to
  it, in backticks (`references/guide.md`). The validator checks that every
  referenced file exists and warns about bundled files nobody references.
- Write skills, and every artifact they produce (plans, tickets, pages), in
  English. Reports shown in chat follow the user's language.
- Explain why a rule exists instead of only stating it: a model that knows
  the reason handles the cases the rule did not foresee.

## Skills that depend on other skills

Say it in the first lines of the body: "Load the `plans-convention` skill
first". When the skill uses files of the other one, refer to that folder as
`<plans-convention>` (for example
`python3 <plans-convention>/scripts/plans.py`) and say so once.

## Subagents inside skills

Skills that orchestrate subagents keep each subagent's prompt as a brief in
their own `references/` folder, and launch it on the harness's
general-purpose agent (`general-purpose` in Claude Code, `general` in
opencode). The skill is then self-contained: installing it is enough.

A brief:

- stands alone: the subagent knows nothing but the brief, so it never says
  "as discussed";
- states objective, scope (paths it may touch), what is out of scope, and how
  success is checked;
- ends with an exact report format, so the coordinator can act on the
  answer without interpreting prose;
- uses `{{placeholders}}` for what the coordinator fills in.

Every orchestrating skill also says what to do when the harness has no
subagents: play the roles one at a time, keeping verification as a separate
pass.

## Bundled scripts

- Python 3.9+, standard library only, invoked as `python3 <path>`, so they
  run on Linux, macOS and Windows without installing anything.
- Deterministic work (ids, moving folders, hashes, validation) belongs in a
  script, not in instructions: the model calls it instead of re-deriving it.
- Every script has tests in `tests/`.

## Invoking a skill

- **Claude Code**: the skill itself is registered as `/name`. Nothing else is
  needed.
- **opencode**: skills are model-invoked only, so every skill gets a thin
  wrapper at `commands/<name>.md` so the user can also run `/name`.

Wrapper template:

```markdown
---
description: <same as the skill>
---

Load and follow the `<name>` skill. $ARGUMENTS
```

Do not write wrappers by hand: `python3 scripts/validate.py --fix` creates
or refreshes them from each skill's description, and the validator fails if
one is missing or out of date.

`commands/` is opencode-only: `scripts/install.sh` links it into opencode and
not into Claude Code, where wrappers would collide with the skill's own
`/name`.

## Agents

- One file per agent: `agents/<name>.md`; the body is the agent's prompt.
- Frontmatter keeps the common minimum: `name` and `description`. Claude Code
  requires `name` or it skips the file; opencode accepts it.
- Avoid harness-specific fields in shared files: Claude's `tools` and
  `permissionMode` are unknown to opencode, which silently routes unknown
  fields into provider `options`. When they are needed, use per-harness
  variants.
- `mode: subagent` is opencode-only and ignored by Claude Code; it is safe to
  include.

## Subagents

Only opencode and Claude Code support the Markdown subagent format, so skills
that orchestrate subagents target those two harnesses.

## Evals

Every skill has `evals/<name>.json` with behaviour cases and trigger cases;
see [evals/README.md](../evals/README.md). Add a case whenever a skill
misbehaves in real use, before fixing it.

## Checks

Run before every commit (CI runs the same on Linux and macOS):

```bash
python3 scripts/validate.py              # --fix to regenerate wrappers
python3 -m unittest discover -s tests
shellcheck scripts/install.sh
```
