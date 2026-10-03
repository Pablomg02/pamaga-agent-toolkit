---
name: make-plan
description: Turn a feature, refactor, migration or non-trivial fix into a reviewed implementation plan saved as a plan folder - investigates the code and the web with helper subagents, asks the user until nothing is ambiguous, writes plan.md with tasks and verifiable acceptance criteria, and has two independent critics check it. Use when the user asks to plan, design, scope or break down a change ("make a plan", "how should we do X", "turn ticket 0021 into a plan", a plan for a roadmap item). Not for one-file fixes with an obvious solution, nor for goals spanning weeks or months (make-roadmap).
---

# Make a plan

Produce a plan that an implementer with no context can execute and verify
without asking anything. The work is in three loops: understand (investigate
and ask), write, and challenge (critique and triage). Do not write code in
this skill, even if the change looks small; the deliverable is the plan.

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
web can answer. Launch helper subagents for independent questions, in
parallel, each with a narrow question:

| Helper | When | Brief |
| --- | --- | --- |
| Repository explorer | Existing code is involved: architecture, conventions, the code the change touches, test and build commands. | `<research-topic>/references/repo-explorer.md` |
| Researcher, `docs` mode | Libraries, APIs, versions, limits, known issues, migration guides. | `<research-topic>/references/researcher.md` |
| Researcher, `literature` mode | Reliable articles, standards, papers, established practice. | `<research-topic>/references/researcher.md` |

Guidelines:

- Read the briefs and fill every placeholder; a subagent knows only what the
  brief says.
- Spend helpers where they add information. A small repository is faster to
  read yourself; a question you can answer in one search does not need a
  researcher.
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
3. Run the self-review checklist at the end of `references/plan-quality.md`
   and fix what fails.

## 5. Independent critique

Launch two critic subagents in parallel with `references/plan-critic.md`: one
with lens A (soundness), one with lens B (executability). Give them the plan
path, the user's original request in their words, and the repository root.
Do not give them your reasoning or the conversation: they must judge the plan
as an implementer would receive it, and must not see each other's output.

## 6. Triage the feedback

Decide on every issue the critics raise, one of:

- **Apply**: a real problem with a fix that does not change what the user
  asked for. Edit the plan.
- **Reject**: wrong (check the evidence yourself), already covered, or not
  worth the cost. Write down why.
- **Ask the user**: the fix changes scope, cost or behaviour the user cares
  about, or the critics disagree on something that matters. Batch these
  questions as in step 3, and record the answers as decisions.

Critics can be wrong. Verify claims about the code before acting on them, and
never apply a fix just because it was suggested.

Write `plan-review.md` in the plan folder: for each issue, the critic (A/B),
severity, a one-line summary and the disposition with its reason. Decisions
that came from the review go in the *Decisions* table with source `review`.

If triage changed the plan substantially (new tasks, a different approach),
run one more critique round on the new version. Stop after that round; ask
the user about anything still contested instead of looping.

## 7. Hand off

- If the plan derives from a roadmap, update that roadmap's *Derived plans*
  table with the new id.
- If the plan folder has a `plan.html`, follow the generated page rule in
  `plans-convention` (check once, remind, offer; never regenerate silently).
- Run `plans.py validate`.
- Report to the user: plan id and path, a five-line summary (goal, approach,
  number of tasks, main risks), what the critique changed, and anything you
  rejected that they may want to know about. Suggest `implement-plan <id>` as
  the next step; do not start implementing.

## Red flags

Stop and correct course if you catch yourself:

- Writing the plan before the user answered the questions that shape it.
- Putting "TBD", "to be decided" or "investigate later" in a task instead of
  asking or deciding now.
- Citing a file, function or command you have not seen.
- Passing the critics a summary instead of the plan file, or telling them what
  to ignore.
- Applying every critic suggestion without checking it, or dismissing a
  serious one without evidence.
- Starting the implementation "since it is quick".
