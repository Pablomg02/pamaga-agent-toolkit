---
name: ship-work
description: Close the loop on finished work in git - commit only, commit and push, or commit, push and open a pull request, as the user chooses. Reviews what is about to be included, writes the commit message in the repository's style and the PR description from the plan when there is one, and never force-pushes or bypasses hooks. Use when the user says "commit this", "push it", "open a PR", "ship it", "wrap this up" or asks to deliver the changes. Not for reviewing the changes (deep-review) or implementing a plan (implement-plan).
---

# Ship the work

Turn changes in the working folder into commits, and optionally a pushed
branch and a pull request. Each of those steps is visible to other people, so
the user chooses how far to go, and nothing goes out that they have not seen
listed.

## 1. Choose how far to go

| Option | What happens |
| --- | --- |
| Commit only | Commit on the current branch. Nothing leaves the machine. |
| Commit and push | Also push the branch to its remote. |
| Commit, push and PR | Also open a pull request (ready or draft). |

If the user's words already decide it ("commit this", "open a draft PR"),
take that. Otherwise ask, with *commit only* as the default unless the
context points elsewhere. Ask in the same batch anything else that is
genuinely open: the branch (see step 3), draft or ready, the target branch.

## 2. Look at what would be included

1. Read `git status` and the full diff, staged and unstaged, and the last
   commits (`git log`), to learn the repository's message style.
2. Find the plan, if any: a plan id mentioned in the conversation, or an
   `in-progress` plan whose tasks match the changes (load the
   `plans-convention` skill to look it up). Its *Justification* and
   *Results* are the best source for the why.
3. List for the user, briefly, what goes in. Leave out and point out
   anything that should not be committed: secrets or credentials, `.env`
   files, large binaries, build output, editor files, debug logging left
   behind. Point out unrelated changes too, and ask whether they go in the
   same commit, a separate one, or stay out.
4. If the project has a fast check (lint, unit tests) and it has not run
   since the last change, run it. If it fails, report it and ask before
   committing.

## 3. Commit

- **Branch.** For *commit only*, commit where the user is. If a push or PR is
  wanted and the current branch is the default branch (`main`, `master`),
  propose a new branch named after the work (`0042-add-search`,
  `fix-empty-export`) and create it before committing; never push straight
  to the default branch unless the user explicitly says so.
- **Grouping.** One commit per logical change. If the diff mixes independent
  changes, propose how to split them; otherwise one commit is fine.
- **Message.** Follow the repository's style. Without one: a short
  imperative subject (under ~70 characters), a blank line, and a body that
  says why, not what the diff already shows. Reference the plan id when
  there is one (`0042: add search index`), and add any trailer the
  repository or the harness requires.
- Stage exactly what step 2 listed: files or folders by path, and only
  folders whose whole content you reviewed. Never stage the whole repository
  at once (`git add -A` or `git add .` at the root), so excluded and unseen
  files stay out. Check the staged list before committing.
- If a hook fails, fix the cause and create the commit again. Never bypass
  hooks (`--no-verify`) unless the user asks.

## 4. Push

Push the branch and set its upstream. If the push is rejected because the
remote moved, fetch and tell the user; rebase or merge only with their
agreement. Never force-push, never rewrite commits that were already pushed,
and never push tags, unless the user explicitly asks.

## 5. Pull request

Use the forge's CLI if it is available and authenticated (`gh` for GitHub,
`glab` for GitLab). If it is not, give the user the compare URL and the
title and description ready to paste.

- **Title**: like a good commit subject, for the change as a whole.
- **Description**, in the language the repository uses (English by default):

  ```markdown
  ## Summary
  <what changes and why, 2-4 lines>

  ## Changes
  - <main change>

  ## How it was verified
  - <tests run, commands, manual checks>

  ## Follow-ups
  - <what is left, with ticket ids if any>

  Plan: 0042
  ```

  Drop sections with nothing to say. Take the why and the verification from
  the plan and from what actually ran, never from memory or assumption, and
  add any footer the harness requires.
- Target the branch the user named, or the default branch.

## 6. Report

In one short block: the commits (hash and subject), the branch and whether
it was pushed, and the PR URL. If the work belongs to a plan that is not
closed yet, mention it; closing plans is `implement-plan`'s job, not this
one's.

## Red flags

- Pushing or opening a PR when the user only asked to commit.
- Staging the whole repository, or a folder with files nobody looked at.
- Force-pushing, `--no-verify`, or amending a commit that was already
  pushed, without the user asking.
- A PR description that claims tests passed when they were not run.
- Pushing straight to `main`.
