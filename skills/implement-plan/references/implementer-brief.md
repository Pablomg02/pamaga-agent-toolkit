# Implementer brief

Fill every placeholder and send the text below as the subagent's task. The
implementer knows only what this brief says, so it must stand on its own:
describe this task, not the history of the session. Copy acceptance criteria
and relevant decisions verbatim from the plan; do not paraphrase them.

For a retry, use the same brief and fill the *Previous attempt* section with
the verifier's findings, verbatim.

---

You are implementing one task of an approved plan. Do this task and nothing
else.

**Repository root:** {{repo_root}}
**Plan:** {{plan_path}} (read the *Justification* and *Approach* sections for
context; do not implement other tasks)

## Task {{task_id}} — {{task_name}}

**Objective:**
{{objective}}

**Scope — files you may create or modify:**
{{files}}

**Out of scope:** anything not needed for this objective, including
refactors, formatting and fixes elsewhere, even if you notice problems. Report
them instead.

**Acceptance criteria (verbatim from the plan):**
{{criteria}}

**Decisions and constraints that apply (verbatim):**
{{decisions}}

**What earlier tasks produced that you build on:**
{{interfaces}}
<!-- exact names, signatures, paths; "none" for the first task -->

**Project commands:** test `{{test_cmd}}`, lint `{{lint_cmd}}`, build `{{build_cmd}}`

**Previous attempt (retries only):**
{{verifier_findings}}

## How to work

- Read the code you are about to change and follow the conventions around it.
- Add or update tests for the behaviour you change, in the project's existing
  test style, unless the criteria say otherwise.
- Run the relevant tests and linters before reporting. Do not report success
  on work you have not run.
- Do not commit, push, or change git state. The coordinator handles git.
- If you need a file outside the scope, a decision the plan does not make, or
  something is blocking you, stop and report it instead of guessing.

## Report

Reply in this format, and nothing else:

```
## Status
DONE | DONE_WITH_CONCERNS | NEEDS_DECISION | BLOCKED

## Changes
- <path> — <what changed>

## Criteria
- [x] <criterion> — <how you checked it: command and result>
- [ ] <criterion> — <why it is not met>

## Commands run
- `<command>` → <pass/fail, key output>

## Concerns, decisions needed or blockers
- <item, with the options you see>   (or "none")

## Noticed but out of scope
- <path:line> — <issue>   (or "none")
```
