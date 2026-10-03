---
name: implement-plan
description: Implement a plan folder, or a small, concrete change the user asks for directly - works through the tasks itself, or with subagents when the plan's Execution section says so, writes and runs tests, proves every acceptance criterion with a command and its output, and leaves the changes uncommitted for the user to check. Records progress and results in the plan when there is one. Use when the user says "implement plan 0042", "execute the plan", "resume plan 0007", or asks for a bounded change in this repository ("add a --dry-run flag to the export command"). Not for designing a change that still has open decisions (make-plan).
---

# Implement

Build exactly what was decided, and prove it works. Design decisions are
not taken here: they come from the plan or from the user's request. That is
what lets a small, cheap model implement safely. Whoever writes the code is
responsible for testing it: nobody checks the work while it is being built,
and a later review re-runs the evidence, so the evidence for every
criterion has to be real (a command you ran and its output).

Load the `plans-convention` skill first when working from a plan.
`<plans-convention>` below stands for the folder that skill was loaded from.

## 1. Know what to build

**From a plan.** The user names a plan by id or path (`plans.py find <ref>`),
or asks to implement or resume one (`plans.py list --status in-progress`,
then `--status backlog`; confirm the candidate, or ask which if several fit).

- `type: roadmap`: roadmaps are not implemented directly. List its derived
  plans and stop.
- `type: ticket`: fine if it passes the readiness check below; otherwise
  suggest promoting it with `make-plan`.
- Folder in `done/`: ask whether to reopen it before doing anything.
- Folder in `in-progress/` with a ledger: this is a resume. Read the ledger,
  check that the repository matches it, and continue from the first task not
  marked done.

**From a direct request.** No plan folder: the user describes the change.
Restate it in chat as a short contract before writing code:

```
Change: <what will be different, in one or two sentences>
Files: <the files you expect to touch>
Out of scope: <tempting adjacent work you will not do>
Done when: <the checks that prove it, as commands or observable behaviour>
```

Find the files and the test commands in the code yourself; ask the user only
what the code cannot answer and would change the result. If the request
needs design decisions (several reasonable approaches with different
trade-offs), touches several unrelated concerns, or would take more than a
few tasks, say so and suggest `make-plan` instead of improvising a design.

## 2. Readiness check (plans)

Read `plan.md` in full. Open the artifacts it links (research notes) only
when a task needs them. Before touching any code, list every point where you
would have to guess:

- tasks without exact files or without verifiable acceptance criteria;
- anything under *Open questions*, any `TBD` or placeholder;
- decisions the plan implies but does not state;
- contradictions between sections, or between the plan and the code as it is
  now (the code may have changed since the plan was written).

Ask the user about every point, batched (up to four questions at a time,
with your recommended option first), and write each answer into the plan
*before* starting: in the *Decisions* table with source `user`, or by fixing
the task it clarifies. A clarification that lives only in the conversation
is lost on the next session. If most tasks fail the check, recommend going
back to `make-plan` instead of patching the plan here.

## 3. Prepare

1. With a plan: `plans.py move <id> in-progress`.
2. Find the project's test, lint and build commands (plan, README, CI config,
   package files).
3. Record a baseline: run the test suite once and note what already fails,
   so pre-existing failures are not blamed on this change. With a plan,
   write it at the top of *Implementation*.

## 4. Implement

Follow the plan's *Execution* section. Without one (a direct request, or an
older plan), work as a single agent.

How to write the code is yours to decide. Anything that would change the
resulting behaviour or outcome (what the user gets, what other code sees)
is not: if the plan or the request does not settle it, stop and ask.

**Single agent.** Take the tasks in order. For each one:

1. Read the code you are about to change and follow its conventions.
2. Write or update the tests for the behaviour the task changes, in the
   project's test style, and run them: they must fail, for the reason the
   task addresses. A test that passes before the change proves nothing.
3. Make the change. Run the relevant tests and linters, and fix what fails.
4. Check every acceptance criterion and note the evidence: the command and
   its result, or the file and line.
5. With a plan, update its ledger line before going to the next task.

**Subagents.** One subagent per package from the *Execution* section, with
`references/implementer-brief.md`. Launch packages that can run at the same
time together (never more than three, never two that share files), and wait
for them before launching the ones that depend on them. Each subagent tests
and proves its own package; you do not re-review its code. When a report
comes back:

- `DONE`: record its evidence in the ledger.
- `NEEDS_DECISION`: ask the user, record the answer in *Decisions*, and send
  the subagent the answer (or a new brief).
- `BLOCKED`: missing context → re-brief with it. A flaw in the plan → stop
  and ask the user how to amend it; record the amendment as a deviation.

When every package is done, run the full test suite, lint and build
yourself: packages that pass alone can still break each other.

## 5. Prove it works

Before calling the work done, check all of this on the real files:

- The full test suite passes, apart from the baseline failures.
- Every acceptance criterion (and the plan's *Verification* section, or the
  contract's *Done when*) has evidence you produced: a command and its
  output, or a file and line. A criterion without evidence is not met.
- Every new test was seen failing before its change (step 4). Do not undo
  your changes to check it afterwards: the work is uncommitted, and
  stashing or reverting it can lose it.
- The diff (`git status` and `git diff`) contains only what was asked: no
  debug code, no `TODO` or stub left behind, no disabled or deleted tests,
  no hard-coded results, no files outside the scope.

When a failure's cause is not obvious, do not try changes at random: follow
the method of the `find-bug` skill (reproduce, test one hypothesis at a
time, fix the root cause). If something still does not converge (the
same criterion keeps failing, or something outside the scope blocks it),
stop and tell the user: what fails, what you tried, what you think the cause
is, and the options (amend the plan, give more context, take over, abandon).
Never relax a criterion, skip a test, or mark a task done to get past it.

## 6. Finish

Leave every change uncommitted: the user decides when it is good enough to
commit. Do not create or switch branches, and never push.

**Direct request.** Report in chat: what changed (files), the evidence for
each *Done when* check, and anything you noticed but left out of scope.
Nothing else to write.

**Plan.**

1. Fill *Results*: what was delivered against each goal, with evidence (test
   output, commands, files), and anything not delivered.
2. Ask the user to confirm the closure. Then fill *Closure* (date, outcome,
   follow-ups; offer to capture follow-ups with `new-ticket`) and run
   `plans.py move <id> done`.
3. If the plan has a `parent` roadmap, update the plan's row in the
   roadmap's *Derived plans* table and add a line to its *Implementation*
   log.
4. Apply the generated page rule if there is a `plan.html`.
5. Run `plans.py validate`.

Then offer the next steps, without starting them: `deep-review` of the
changes, `ship-work` to commit (and push or open a pull request), and
`save-learning` if the work taught something non-obvious.

## Ledger format

The ledger lives in the plan's *Implementation* section. It survives context
compaction and new sessions, so update it after every task, not at the end.

```markdown
Baseline (2026-10-03): 2 failing tests — test_legacy_export, test_flaky_io

- [x] T1 — add search index — `pytest tests/test_index.py` 6 passed
- [x] T2 — query parser — `pytest tests/test_parser.py` 11 passed; empty query returns []
- [ ] T3 — rename config keys — in progress (package P2)
- [ ] T4 — UI — pending

Deviations:
- T2: also changed `src/util/text.py` (normalise accents); approved by user 2026-10-03.
```

## Subagents

Launch subagents with your harness's task tool, using its general-purpose
agent (`general-purpose` in Claude Code, `general` in opencode). Each one
starts with no memory: the brief is all it knows, so never write "as
discussed" or "like before". If no subagents are available, implement the
packages yourself, one after another.

## Red flags

- Writing code while the plan still has open questions, or while a direct
  request still needs a design decision.
- Choosing something that changes the result (behaviour, output, what
  other code sees) when the plan or the user did not decide it.
- Marking a criterion met without a command or file you checked yourself.
- Weakening a test or a criterion so it passes.
- A clarification that is in the conversation but not in `plan.md`.
- Subagents that share files, or more than three at once.
- Committing, creating branches, or pushing.
