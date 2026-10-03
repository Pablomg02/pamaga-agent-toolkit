---
name: implement-plan
description: Implement an existing plan folder by coordinating subagents - one brief per task with scope and acceptance criteria, an independent verifier that checks the real files and tests against the plan, and bounded retries. Requires a plan created with make-plan; without one it stops. Use when the user says "implement plan 0042", "execute the plan", "start working on the plan", or wants to resume a plan that is in progress.
---

# Implement a plan

You are the coordinator. You make sure the plan is unambiguous, brief one
implementer per task, have an independent verifier check the real result
against the plan, and keep the plan's ledger up to date. You do not write the
code yourself: keeping the roles separate is what makes the verification
honest.

Load the `plans-convention` skill first. `<plans-convention>` below stands
for the folder that skill was loaded from.

## 1. Find the plan

- The user names a plan by id or path: `plans.py find <ref>`.
- The user names none: `plans.py list --status in-progress`, then
  `--status backlog`. If exactly one candidate fits the request, confirm it
  with the user; if several do, ask which.
- **No plan folder exists**: tell the user that this skill implements an
  existing plan, suggest `make-plan`, and stop. Do not improvise a plan.
- `type: roadmap`: roadmaps are not implemented directly. List its derived
  plans and stop.
- `type: ticket`: fine if it passes the readiness check below; otherwise
  suggest promoting it with `make-plan`.
- Folder in `done/`: ask whether to reopen it before doing anything.
- Folder in `in-progress/` with a ledger: this is a resume. Read the ledger,
  check that the repository matches it (files exist, tests state), and
  continue from the first task not marked done.

## 2. Readiness check

Read `plan.md` in full and every artifact it links. Before touching any code,
list every point where an implementer would have to guess:

- tasks without exact files or without verifiable acceptance criteria;
- anything under *Open questions*, any `TBD` or placeholder;
- decisions the plan implies but does not state;
- contradictions between sections, or between the plan and the code as it is
  now (the code may have changed since the plan was written).

Ask the user about every point, batched (up to four questions at a time, with
your recommended option first). Write each answer into the plan *before*
starting: in the *Decisions* table with source `user`, or by fixing the task
it clarifies. The plan must remain the single source of truth; a
clarification that lives only in the conversation is lost on the next
session.

If the plan is fundamentally underspecified (most tasks fail the check),
recommend going back to `make-plan` instead of patching it here.

Also ask how to handle git, unless the plan already says:

| Option | Behaviour |
| --- | --- |
| No commits | Leave all changes uncommitted for the user. |
| Commit per task | One commit per verified task on the current branch. |
| Branch + commit per task | Create `plan/<id>-<slug>` first, then one commit per verified task. |
| Worktree + commit per task | Follow the `concurrent-work` skill with slug `plan-<id>`: own branch and folder, one commit per verified task. Recommend it when that skill's board shows other agents working. |

Never push. Record the choice in *Implementation* as `Git policy: ...`. With
the worktree option, every verified task is a `concurrent-work` checkpoint
(ping, check the board, rebase if the base moved).

If you edited `plan.md` and the folder has a `plan.html`, follow the generated
page rule in `plans-convention`.

## 3. Prepare

1. `plans.py move <id> in-progress`.
2. Find the project's test, lint and build commands (plan, README,
   CI config, package files).
3. Record a baseline: run the test suite once and note what already fails, so
   pre-existing failures are not blamed on the plan.
4. Start the ledger in *Implementation* (format below).
5. Order the tasks by their dependencies. Tasks may run in parallel only when
   they are independent *and* touch disjoint files; when in doubt, run them
   in sequence.

## 4. Task loop

For each task:

1. **Brief.** Fill `references/implementer-brief.md`: objective, scope and
   paths, acceptance criteria and decisions copied verbatim, the interfaces
   earlier tasks produced, project commands, and the report format. Several
   identical small edits across files go in a single brief.
2. **Implement.** Launch one implementer subagent with the brief.
3. **Handle the report.**
   - `DONE` / `DONE_WITH_CONCERNS`: go to verification; keep the concerns.
   - `NEEDS_DECISION`: ask the user, record the answer in *Decisions*, and
     re-brief. This does not count as a retry.
   - `BLOCKED`: work out why. Missing context → re-brief with it. A flaw in
     the plan → stop and ask the user how to amend the plan; record the
     amendment as a deviation.
4. **Verify.** Launch a fresh verifier subagent with
   `references/verifier.md`. Give it the criteria, the expected files, how to
   see the diff, the baseline, and the implementer's claims as things to
   check. Never skip verification, and never accept the implementer's report
   as proof.
5. **Retry if needed.** On `FAIL`, re-brief the implementer with the
   verifier's *Findings for a retry* verbatim, then verify again. At most two
   retries per task (three attempts in total). If it still fails, stop the
   loop and go to step 6.
6. **Record.** Update the ledger line for the task. If the git policy says
   so, commit the task's changes with a message that names the plan and task
   (`0042 T3: add token refresh`).

## 5. Final verification

When every task is done, launch one verifier for the whole plan: the plan's
*Verification* section plus all task criteria, the full test suite against
the baseline, and the full diff since the start. Treat a `FAIL` like a task
failure: brief one implementer with all the findings, verify again, at most
two retries.

Then offer the user a `deep-review` of the changes; it looks for problems
the acceptance criteria do not cover.

## 6. Stop when it does not converge

When a task exhausts its retries, or something outside the plan blocks the
work, stop and report to the user:

- which task, what was attempted, and the verifier's latest findings;
- what you think the cause is (plan flaw, missing information, environment);
- the options: amend the plan, give more context, take over manually, or
  abandon.

Record the situation in the ledger. Do not keep retrying, lower the criteria,
or mark the task done.

## 7. Close

1. Fill *Results*: what was delivered against each goal, with evidence (test
   output, commands, files), and anything not delivered.
2. Ask the user to confirm the closure. Then fill *Closure* (date, outcome,
   follow-ups; offer to capture follow-ups with `new-ticket`) and run
   `plans.py move <id> done`.
3. If the plan has a `parent` roadmap, update the plan's row in the
   roadmap's *Derived plans* table and add a line to its *Implementation* log.
4. Apply the generated page rule if there is a `plan.html`.
5. Run `plans.py validate`.

## Ledger format

The ledger lives in the plan's *Implementation* section. It survives context
compaction and new sessions, so update it after every task, not at the end.

```markdown
Git policy: commit per task (branch plan/0042-add-search)
Baseline (2026-10-03): 2 failing tests — test_legacy_export, test_flaky_io

- [x] T1 — add search index — verified, 1 attempt — commit 3f2a91c
- [x] T2 — query parser — verified, 2 attempts (first failed: empty query crashed)
- [ ] T3 — API endpoint — in progress, attempt 1
- [ ] T4 — UI — pending

Deviations:
- T2: also changed `src/util/text.py` (normalise accents); approved by user 2026-10-03.
```

## Subagents

Launch subagents with your harness's task tool, using its general-purpose
agent (`general-purpose` in Claude Code, `general` in opencode). Each one
starts with no memory: the brief is all it knows, so never write "as
discussed" or "like before". If the harness lets you choose models, use a
cheaper one for mechanical tasks and a capable one for verification. If no
subagents are available, play each role yourself in turn, and do the
verification as a separate pass that re-reads the files and re-runs the
commands instead of relying on what you remember writing.

## Red flags

- Starting a task while the plan still has open questions.
- Writing or fixing code yourself instead of re-briefing the implementer.
- Marking a task done from the implementer's report without a verifier PASS.
- A clarification that is in the conversation but not in `plan.md`.
- Retrying a third time, or relaxing a criterion so it passes.
- Committing when the git policy says not to, or pushing at all.
