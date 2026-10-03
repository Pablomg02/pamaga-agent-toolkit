---
name: concurrent-work
description: Opt-in isolation for agents working on the same repository at once - each one works on its own branch in its own git worktree and registers on a shared board (.git/agent-work/) that shows who is doing what, flags overlapping paths and stale sessions, and integrates early. Use only when the user explicitly asks for it - mentions several agents or sessions working on the repository at the same time, asks to work in a separate worktree or isolated branch, asks who else is working here, or names this skill. Not for ordinary edits, even large ones.
---

# Concurrent work

Several agents can work on the same repository at once if each one stays on
its own branch, in its own folder (a git worktree), and they can see each
other. The board makes them visible: one short note per agent in
`.git/agent-work/`, shared by every worktree and never committed.

This skill is opt-in: use it only when the user asked for it. Ordinary work
happens in the user's folder and branch, with no board, branch or worktree.

The risk with separate branches is drifting apart for hours and colliding at
merge time. The rules below keep everyone visible and integrate early, so a
collision shows up as a warning at the start or a small conflict in the
middle, not a mess at the end.

`scripts/work.py` (relative to this file, Python 3.9+) does the bookkeeping.
Run it from anywhere inside the repository.

## 1. Look at the board

```bash
python3 scripts/work.py list
```

Read what others are doing, which paths they touch, and what they ask others
to expect (for example "the signature of `login()` changes"). Take it into
account in your own work. Notes marked `STALE` have had no sign of life for
over two hours: mention them to the user, do not delete them yourself.

Read-only work (answering questions, reviews that change nothing) stops
here: it needs no note, branch or worktree.

## 2. Start

```bash
python3 scripts/work.py start <slug> --task "<one line>" --paths "<paths or globs>" [--expect "<one line>"]
```

- `slug`: short name for the work (`fix-export`). It names the branch
  `work/<slug>`.
- `--paths`: comma-separated paths or globs you expect to modify
  (`src/export/**,docs/export.md`). Be specific; the script uses them to
  detect overlaps.
- `--expect`: anything that will affect others once merged. Omit it if
  nothing will.

If the paths overlap with someone else's work, the script stops and creates
nothing. Tell the user who is working on what, and let them choose: wait,
narrow your paths, or go ahead anyway (retry with `--allow-overlap`).

Otherwise it creates your branch from the current branch of the main folder,
a worktree at `../<repo>-work/<slug>`, and your note. From now on, **do all
your work inside that worktree**: edit files there, run commands there. The
main folder belongs to the user.

A new worktree has only committed files. If the project needs untracked
things to run (`.env`, `node_modules`, a virtualenv, build outputs), copy or
install them in the worktree before running anything.

## 3. While working

- Commit to your branch in small steps.
- At every checkpoint (after each commit, each finished task, or about every
  30 minutes):
  1. `python3 scripts/work.py ping <slug> --progress "<one line>"`
  2. `python3 scripts/work.py list`, to notice new work or `expect` notes.
  3. If the base branch has moved (someone merged), rebase now:
     `git rebase <base>`. Small conflicts now are cheap; the same conflicts
     after a day of work are not.
- If you need to modify paths outside the ones you declared, check the board
  first. If they belong to someone else's work, ask the user.
- Never touch another agent's worktree or branch, and never commit to the
  base branch directly.

## 4. Finish

1. Commit everything. Rebase on the latest base branch and run the tests.
2. `python3 scripts/work.py ping <slug> --status finished --progress "ready to merge"`
3. Tell the user: the branch, what changed, the test result, and anything in
   `--expect` that others must now take into account. Ask whether to merge.
4. If they agree, merge from the main folder: `git merge --ff-only work/<slug>`
   (the rebase makes it a fast-forward). If the main folder has uncommitted
   changes or is on another branch, ask the user instead of forcing anything.
   Never push unless asked.
5. Clean up, from the main folder: `python3 scripts/work.py end <slug>`. It
   removes your note and worktree, and deletes the branch if it is merged.

If the work is abandoned, ask the user before `end <slug> --force`, which
discards uncommitted changes and the unmerged branch.
