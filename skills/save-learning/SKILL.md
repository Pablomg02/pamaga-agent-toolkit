---
name: save-learning
description: Save a short, reusable lesson as a note in docs/learnings/ - the context, the lesson, why it holds, an example and when it applies - citing the plan, roadmap or ticket it came from by id, and list it in the folder's index. Only for insights that are non-obvious and useful beyond the task at hand; says so instead of writing when nothing qualifies. Use when the user says "save this learning", "write down what we learned", "note this lesson" or "add it to the learnings", or accepts an offer to save one after a plan, a debugging session or a research. Not for tasks still to do (new-ticket) or for project rules the agent must always follow.
---

# Save a learning

A learning is something we found out the hard way and would like to know
next time: a library's real behaviour, why an approach failed, a trick that
made something work. Written down briefly, it teaches whoever reads it,
person or agent, in a minute. Written down at length or for everything, the
folder becomes a changelog nobody reads, so the bar matters as much as the
writing.

Load the `plans-convention` skill first when the work relates to a plan.

## 1. Decide whether it deserves a note

Find the lesson in the conversation, the plan, the debugging report or the
research the user is referring to. Then check it against the bar:

- **Non-obvious**: a competent developer would not have known it in advance.
- **Reusable**: it helps beyond this task: in another feature, project or
  decision.
- **Explained**: we know *why* it holds, not only that it happened once.
- **Not recorded elsewhere**: not already obvious from the code, a comment,
  the docs or the commit history.

If it fails the bar, tell the user why in one line and suggest the right
place instead (a code comment, the README, a ticket). If the conversation
holds several lessons, propose the ones that pass, one line each, and let
the user pick. A rule the agent must follow on every task in this project
belongs in the project's agent instructions file (`AGENTS.md`, `CLAUDE.md`),
not here; offer that instead.

## 2. Avoid duplicates

Read `docs/learnings/README.md` and search the folder for the topic. If a
note already covers it, update that note (add the new case, sharpen the
lesson, add the source) instead of writing a second one.

## 3. Write the note

Create `docs/learnings/<slug>.md` from `templates/learning.md`. The slug is
the lesson in a few words (`sqlite-wal-needs-shared-memory`), not the task
(`plan-0042-notes`).

- **Title**: the lesson as a claim ("SQLite in WAL mode needs shared
  memory, so it fails on network drives"), not a topic ("SQLite notes").
- **Brief**: the whole note fits on one screen. Cut the story of how it was
  found; keep the lesson, the why and the smallest example.
- **Sources**: cite the plan, roadmap or ticket by id (`0042`), never by
  path, because folders move when their status changes; add the commit, PR
  or external source when they help. If the lesson does not come from a
  plan, leave `source` empty.
- Write it in English, like every artifact of the toolkit, and verify every
  fact, path and snippet in it: a wrong learning is worse than none.

## 4. Update the index

Add one line to `docs/learnings/README.md`, creating it with a
`# Learnings` title if it does not exist, and keep the list sorted by date,
newest first:

```markdown
- [SQLite in WAL mode needs shared memory](sqlite-wal-needs-shared-memory.md) — 2026-10-03 · from 0042
```

## 5. Link back and report

If the lesson comes from a plan, add a line to that plan's *Closure* (or
*Implementation*, if it is still open):
`Learning: docs/learnings/<slug>.md`. Then report the path and the lesson in
one line each.

## Red flags

- A note that retells what happened instead of what we learned.
- A lesson without its why.
- Saving something obvious, or something the code already says.
- Citing a plan by path, or a plan id that does not exist.
- A second note on a topic that already has one.
