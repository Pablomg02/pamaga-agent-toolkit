---
name: implement-plan
description: Execute an existing plan folder as a coordinator - briefs implementer subagents (short related tasks grouped together, at most three in parallel), has an independent verifier check the real files and tests against the acceptance criteria, retries at most twice, and keeps the plan's ledger up to date. Use when the user says "implement plan 0042", "execute the plan", "start working on the plan" or wants to resume a plan in progress. Requires a plan folder; without one it stops and suggests make-plan.
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

Also ask how to handle git, in the same batch, unless the plan already says:

| Option | Behaviour |
| --- | --- |
| No commits | Leave all changes uncommitted for the user. |
| Commit per task | One commit per verified task on the current branch. |

Work on the branch and folder the user is on: do not create or switch
branches, and never push. Record the choice in *Implementation* as
`Git policy: ...`.

## 3. Prepare

1. `plans.py move <id> in-progress`.
2. Find the project's test, lint and build commands (plan, README,
   CI config, package files).
3. Record a baseline: run the test suite once and note what already fails, so
   pre-existing failures are not blamed on the plan.
4. Start the ledger in *Implementation* (format below).
5. Group the tasks into units and waves, and write the grouping in the
   ledger:
   - **Unit**: what one implementer gets. Usually one task. Short related
     tasks (a few lines in one or two files, mechanical edits, the same
     change in several places) go together in one unit, so small work does
     not cost a subagent pair per task. Keep a unit small enough to verify in
     one pass.
   - **Wave**: units that run at the same time. Up to **three** units that do
     not depend on each other and touch disjoint files; when in doubt, one
     unit per wave. Implementers share one working folder, so more of them
     at once means more chances of stepping on each other's files, builds
     and test runs.

## 4. Wave loop

For each wave, in dependency order:

1. **Brief.** Fill `references/implementer-brief.md` for each unit:
   objective, scope and paths, acceptance criteria and decisions copied
   verbatim, the interfaces earlier tasks produced, project commands, and the
   report format.
2. **Implement.** Launch the wave's implementers in parallel (at most three)
   and wait for all of them before going on.
3. **Handle the reports.**
   - `DONE` / `DONE_WITH_CONCERNS`: go to verification; keep the concerns.
   - `NEEDS_DECISION`: ask the user, record the answer in *Decisions*, and
     re-brief. This does not count as a retry.
   - `BLOCKED`: work out why. Missing context → re-brief with it. A flaw in
     the plan → stop and ask the user how to amend the plan; record the
     amendment as a deviation.
4. **Verify.** Launch one fresh verifier for the whole wave with
   `references/verifier.md`. Give it each unit's criteria, expected files and
   implementer claims (as things to check), how to see the changes, the
   baseline, and the files earlier waves changed, so it does not mistake
   their work for this wave's. Never skip verification, and never accept an
   implementer's report as proof.
5. **Retry if needed.** For each unit with `FAIL`, re-brief its implementer
   with the verifier's findings for that unit verbatim, then verify the
   retried units again with one fresh verifier. At most two retries per unit
   (three attempts in total). If a unit still fails, stop and go to step 6.
6. **Record.** Update the ledger line of each task. If the git policy says
   so, commit each unit separately with a message that names the plan and
   its tasks (`0042 T1: add search index`, `0042 T3+T4: rename config
   keys`).

## 5. Final verification

When every task is done, launch one verifier for the whole plan: the plan's
*Verification* section plus all task criteria, the full test suite against
the baseline, and the full diff since the start. Treat a `FAIL` like a task
failure: brief one implementer with all the findings, verify again, at most
two retries.

Then offer the user a `deep-review` of the changes; it looks for problems
the acceptance criteria do not cover.

## 6. Stop when it does not converge

When a unit exhausts its retries, or something outside the plan blocks the
work, stop and report to the user:

- which unit and tasks, what was attempted, and the verifier's latest findings;
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
Git policy: commit per task
Baseline (2026-10-03): 2 failing tests — test_legacy_export, test_flaky_io
Waves: 1 = T1, T2 · 2 = T3+T4 (one unit) · 3 = T5

- [x] T1 — add search index — verified, 1 attempt — commit 3f2a91c
- [x] T2 — query parser — verified, 2 attempts (first failed: empty query crashed) — commit 8be01d4
- [ ] T3 — rename config keys — in progress, attempt 1
- [ ] T4 — update config docs — in progress, attempt 1
- [ ] T5 — UI — pending

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
- More than three implementers at once, or parallel units that share files.
- Retrying a third time, or relaxing a criterion so it passes.
- Committing when the git policy says not to, creating branches, or pushing.
