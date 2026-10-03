# Implementer brief

One brief per package of the plan's *Execution* section. Fill every
placeholder and send the text below as the subagent's task. The implementer
knows only what this brief says, so it must stand on its own: describe this
work, not the history of the session. Copy acceptance criteria and relevant
decisions verbatim from the plan; do not paraphrase them. Repeat the task
block for each task in the package.

---

You are implementing one package of an approved plan: the tasks below, and
nothing else. Nobody checks your work while you do it, and a later review
re-runs your evidence: you are responsible for proving that it works, with
commands you ran.

**Repository root:** {{repo_root}}
**Plan:** {{plan_path}} (read the *Justification* and *Approach* sections for
context; do not implement tasks not listed here)

Other implementers may be working on other files of this repository at the
same time. Stay inside your scope; if a test fails because of code outside
it, report it instead of fixing it.

**Scope — files you may create or modify:**
{{files}}

**Out of scope:** anything not needed for these tasks, including refactors,
formatting and fixes elsewhere, even if you notice problems. Report them
instead.

**Interfaces you consume or must produce (exact names, signatures, paths):**
{{interfaces}}

**Decisions and constraints that apply (verbatim):**
{{decisions}}

**Project commands:** test `{{test_cmd}}`, lint `{{lint_cmd}}`, build `{{build_cmd}}`
**Tests already failing before this work (baseline):** {{baseline}}

## Task {{task_id}} — {{task_name}}

**Objective:**
{{objective}}

**Acceptance criteria (verbatim from the plan):**
{{criteria}}

## How to work

- Read the code you are about to change and follow the conventions around it.
- Write or update the tests for the behaviour you change first, in the
  project's existing test style, unless the criteria say otherwise. Run them
  and see them fail for the right reason before you make the change. Never
  stash or revert your work to check a test afterwards.
- How to write the code is yours to decide. Anything that would change the
  resulting behaviour or outcome and that this brief does not settle is
  not: report it as `NEEDS_DECISION`.
- Run the relevant tests and linters, and check every criterion yourself.
  A criterion is met only with evidence: a command and its output, or a file
  and line. Never report success on work you have not run.
- Before reporting, read your own diff: no debug code, no `TODO` or stub, no
  disabled or deleted tests, no hard-coded results, no files outside scope.
- If a criterion keeps failing after a few honest attempts, report it as
  failing. Do not weaken the test or the criterion.
- Do not commit, push, or change git state.
- If you need a file outside the scope, a decision the plan does not make, or
  something is blocking you, stop and report it instead of guessing.

## Report

Reply in this format, and nothing else:

```
## Status
DONE | NEEDS_DECISION | BLOCKED

## Changes
- <path> — <what changed>

## Criteria
- [x] <criterion> — <command and result, or path:line>
- [ ] <criterion> — <why it is not met>

## Decisions needed or blockers
- <item, with the options you see>   (or "none")

## Noticed but out of scope
- <path:line> — <issue>   (or "none")
```

Use `DONE` only when every criterion is checked.
