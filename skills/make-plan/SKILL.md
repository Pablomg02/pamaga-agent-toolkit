---
name: make-plan
description: Turn a feature, refactor, migration or non-trivial fix into an implementation plan saved as a plan folder - investigates the code (and the web when needed), asks the user until nothing is ambiguous, writes plan.md with tasks, verifiable acceptance criteria and an execution mode (single agent, or subagents only when the work splits into substantial independent packages), and offers an independent critic for large plans. Use when the user asks to plan, design, scope or break down a change ("make a plan", "how should we do X", "turn ticket 0021 into a plan", a plan for a roadmap item). Not for one-file fixes with an obvious solution, nor for goals spanning weeks or months (make-roadmap).
---

# Make a plan

Produce a plan that an implementer with no context can execute and verify
without asking anything. Assume that implementer is a smaller, cheaper model
than you: every design decision is taken here, so implementation is only
following instructions and proving each criterion with a command. The work is
in two loops, understand (investigate and ask) and write, with an optional
critique for large plans. Do not write code in this skill, even if the change
looks small; the deliverable is the plan.

Load the `plans-convention` skill first: it defines the folder, the
`plan.md` template and the script used below. `<plans-convention>` stands for
the folder that skill was loaded from. The investigation briefs belong to the
`research-topic` skill; `<research-topic>` stands for its folder.

## 1. Frame the request

Restate in two or three sentences what the user wants and why, and what
"done" looks like. Then size it:

- **Too small for a plan** (a one-file fix with an obvious solution): say so
  and offer to capture it as a ticket (`new-ticket`) or to just do it. Follow
  the user's choice.
- **Too big for one plan** (several independent deliverables, weeks of work,
  milestones): suggest a roadmap (`make-roadmap`) first, and plan only its
  first item if the user agrees.
- **Derived from a roadmap or a ticket**: read that folder first. A plan from
  a roadmap gets `--parent <roadmap id>`; a plan promoted from a ticket
  replaces it (close the ticket in `done/` pointing to the new plan id).

## 2. Investigate

Find out what exists before asking the user anything the repository or the
web can answer. Read the code yourself by default: you need to know it well
to decide the approach and the execution mode. Helper subagents are for
large repositories or independent external questions, each with a narrow
question, in parallel:

| Helper | When | Brief |
| --- | --- | --- |
| Repository explorer | Existing code is involved: architecture, conventions, the code the change touches, test and build commands. | `<research-topic>/references/repo-explorer.md` |
| Researcher, `docs` mode | Libraries, APIs, versions, limits, known issues, migration guides. | `<research-topic>/references/researcher.md` |
| Researcher, `literature` mode | Reliable articles, standards, papers, established practice. | `<research-topic>/references/researcher.md` |

Guidelines:

- Read the briefs and fill every placeholder; a subagent knows only what the
  brief says.
- Spend helpers only where they add information. A repository you can read
  in a few minutes, or a question one search answers, does not need one.
- Read the key files yourself after the explorers report. Their summaries
  point you to evidence; they are not the evidence.
- Researchers write their reports to `research/<topic>.md` inside the plan
  folder. If the folder does not exist yet, create it now with
  `plans.py new` (step 4) so the artifacts land in their final place.

Launch subagents with your harness's task tool, using its general-purpose
agent (`general-purpose` in Claude Code, `general` in opencode). If no
subagents are available, do the same investigations yourself, one at a time.

## 3. Ask until nothing is ambiguous

Collect every point where the user's intent, a trade-off, or a missing fact
would change the plan. Then ask:

- Batch the questions (up to four at a time), most consequential first. Use
  the harness's question tool if it has one; otherwise ask in chat as a
  numbered list.
- Prefer multiple choice. Put your recommended option first, say why, and
  state what each option implies.
- Never ask what the code, the docs or a quick search can answer.
- Do not ask about details with a sensible conventional default; decide, and
  record the decision so the user can see and override it.

New answers often raise new questions or call for more investigation. Loop
between steps 2 and 3 until there are no open doubts and no helper would add
anything. Then tell the user you are writing the plan.

## 4. Write the plan

1. Create the folder, unless step 2 already did:
   `python3 <plans-convention>/scripts/plans.py new --title "<title>" [--parent <id>]`.
   It starts in `backlog/`.
2. Fill `plan.md` following the template and `references/plan-quality.md`.
   Record every decision taken in step 3 in the *Decisions* table with source
   `user`, and every research conclusion with source `research` and a link to
   its artifact.
3. Decide the *Execution* mode (below) and write it in the plan.
4. Run the self-review checklist at the end of `references/plan-quality.md`
   and fix what fails.

### Execution mode

You know the code and the plan now; the implementer will not have that
overview, so the split is decided here.

- **Single agent** is the default. One agent working through the tasks in
  order keeps the whole change in its head and costs the least.
- **Subagents** only when the work splits into packages that each:
  - touch files no other package touches;
  - depend on other packages only through interfaces the plan fixes
    (names, signatures, paths, formats);
  - can be checked on their own with their tasks' criteria;
  - are substantial enough to be worth a separate agent (several tasks or a
    real chunk of code, not a one-line edit).

  If any package fails one of these, merge it into another or use a single
  agent. Write the packages, their tasks and files, the order (which ones
  can run at the same time, at most three), and one sentence on why the split
  pays off.

## 5. Optional critique

For a large or risky plan (many tasks, subagent execution, data migrations,
security-sensitive code), offer the user one independent critic before
handing off; say what it costs (one subagent) and what it catches (wrong
assumptions about the code, places where the implementer would have to
guess). For a small or medium plan, do not offer it: the self-review is
enough. Without subagents, the critique is a separate pass of your own that
re-reads the plan as its implementer and checks every cited file.

If the user accepts, launch one critic subagent with
`references/plan-critic.md`. Give it the plan path, the user's original
request in their words, and the repository root; not your reasoning or the
conversation, since it must judge the plan as the implementer will receive
it. Then decide on every issue it raises:

- **Apply**: a real problem with a fix that does not change what the user
  asked for. Edit the plan.
- **Reject**: wrong (check the evidence yourself), already covered, or not
  worth the cost. Write down why.
- **Ask the user**: the fix changes scope, cost or behaviour the user cares
  about. Batch these questions as in step 3, and record the answers as
  decisions.

Write `plan-review.md` in the plan folder: for each issue, its severity, a
one-line summary and the disposition with its reason. Decisions that came
from the critique go in the *Decisions* table with source `review`. One round
only; ask the user about anything still contested instead of looping.

## 6. Hand off

- If the plan derives from a roadmap, update that roadmap's *Derived plans*
  table with the new id.
- If the plan folder has a `plan.html`, follow the generated page rule in
  `plans-convention` (check once, remind, offer; never regenerate silently).
- Run `plans.py validate`.
- Report to the user: plan id and path, a five-line summary (goal, approach,
  number of tasks, execution mode, main risks), and what the critique
  changed if there was one. Suggest `implement-plan <id>` as the next step;
  do not start implementing.

## Red flags

Stop and correct course if you catch yourself:

- Writing the plan before the user answered the questions that shape it.
- Putting "TBD", "to be decided" or "investigate later" in a task instead of
  asking or deciding now.
- Leaving a design choice to the implementer ("pick a suitable structure").
- Citing a file, function or command you have not seen.
- Choosing subagents for packages that share files or are too small to be
  worth an agent.
- Starting the implementation "since it is quick".
