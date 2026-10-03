# What makes a plan implementable

The reader of a plan is an implementer with no memory of the conversation that
produced it: often a smaller, cheaper model, a subagent, or the user in
three months. Every line should either inform a decision or decide
something. A plan that needs
its author nearby to be understood is not finished.

## Justification

- States the problem in terms of observable behaviour or a concrete need, not
  in terms of the solution ("users cannot recover a lost password", not "add
  a reset endpoint").
- Goals are checkable. Non-goals name the tempting adjacent work that is out
  of scope, so nobody does it "while they are at it".

## Context

- Cites real paths, functions and commands found in the repository, not
  guesses. If something was not verified, say so.
- Gives the project's test, lint and build commands, so the implementer
  does not have to look for them.
- Links research artifacts stored in the plan folder (`research/*.md`) instead
  of pasting them.

## Approach and decisions

- Explains the chosen approach and the alternatives that were discarded, with
  the reason. A future reader should not reopen a settled discussion.
- Every choice the implementer could otherwise make differently is in the
  *Decisions* table with its source: `user` (asked and answered), `research`
  (backed by an artifact) or `review` (came from the critic).

## Tasks

A task is the smallest unit that can be implemented and verified on its own.
Each one has:

- **Objective**: one or two sentences about the outcome, not the activity.
- **Files**: exact paths to create or modify. A task whose files are unknown
  is not ready.
- **Depends on**: the task ids that must be finished first, or `—`.
- **Acceptance criteria**: checkboxes the implementer can prove by reading files
  or running a command, without asking anyone. Prefer criteria with an exact
  command and expected result:
  - good: "`pytest tests/test_auth.py` passes, including a new test for an
    expired token"
  - good: "`GET /health` returns 200 with body `{\"status\":\"ok\"}`"
  - bad: "authentication works correctly"
  - bad: "code is clean and well tested"

Sizing:

- One task touches one concern. If its criteria list mixes unrelated things,
  split it.
- Several identical small edits across files are one task, not ten.
- Order tasks so each one leaves the repository working (tests pass, it
  builds). Put the riskiest unknown first when possible: it may change the
  rest of the plan.
- Names, signatures and paths introduced in one task are spelled exactly the
  same in every later task that uses them.

## Execution

- States the mode: `single agent` (the default) or `subagents`.
- With subagents, lists each package: its tasks, its files (disjoint from
  every other package), the interfaces it consumes or produces, and which
  packages can run at the same time (at most three). One sentence says why
  the split is worth it.

## Verification

- Lists how the whole plan is proven done: the full test suite, a manual
  scenario, a benchmark, a deployed check. Cross-task criteria live here.

## Risks and open questions

- Risks have a mitigation or an explicit "accepted".
- *Open questions* must be empty before the plan is handed to
  implementation. If something is genuinely undecidable now, turn it into a
  decision ("start with X; revisit in T4 if Y") or a spike task.

## Proportion

The plan is as long as the work needs and no longer. A one-day change fits in
a page. Do not paste code the implementer can derive from the objective and
criteria; include code only when an exact snippet is the decision (a schema,
a public signature, a config value).

## Self-review checklist

Run this before handing the plan off (and before the critic, if there is
one):

1. Every part of the user's request maps to a goal and to at least one task,
   or is listed as a non-goal.
2. Every task has objective, files, dependencies and verifiable criteria.
3. No `TBD`, `TODO`, `etc.`, "as appropriate", "handle errors properly" or
   similar placeholders remain.
4. Names and paths are consistent across tasks.
5. Dependencies form no cycle and the order makes sense.
6. Every decision made in the conversation is in the *Decisions* table.
7. *Open questions* is empty.
8. *Context* gives the test, lint and build commands.
9. No task leaves a design choice to the implementer: a smaller model could
   follow it step by step and prove each criterion with a command.
10. *Execution* names a mode; subagent packages share no files and are each
    worth an agent.
