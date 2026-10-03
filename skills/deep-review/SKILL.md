---
name: deep-review
description: Multi-agent code review. Asks what to review (bugs, security, performance and optimisation, tests, simplification, project conventions, documentation quality, outdated docs) and over what scope, launches one reviewer subagent per theme in parallel, then has independent validators discard false positives before reporting. Use when the user asks for a review, code review, audit or second opinion of changes, a branch, a PR, a folder or a whole repository, or asks to look for bugs, optimisations or outdated docs.
---

# Deep review

Run several focused reviewers instead of one generalist: a reviewer looking
only for security problems finds things a reviewer skimming for everything
misses. Then filter: every finding is checked by a validator that did not
write it, so the user only sees problems that survived an attempt to disprove
them.

This skill reports; it does not change code. Offer fixes at the end.

## Themes

| Theme | File | Group |
| --- | --- | --- |
| Bugs and logic errors | `references/themes/bugs.md` | Correctness |
| Security | `references/themes/security.md` | Correctness |
| Tests | `references/themes/tests.md` | Correctness |
| Performance and optimisation | `references/themes/performance.md` | Performance |
| Simplification and maintainability | `references/themes/simplification.md` | Maintainability |
| Project conventions | `references/themes/conventions.md` | Maintainability |
| Documentation quality | `references/themes/docs-quality.md` | Documentation |
| Outdated documentation | `references/themes/docs-outdated.md` | Documentation |

## 1. Decide what to review

Two things must be clear before reviewing: the **scope** and the **themes**.
Take whatever the user already said ("review src/api for security", "look for
optimisations in this branch") and ask only for what is missing. Ask both in
one round, using the harness's question tool if it has one.

**Scope.** First detect what is there (`git status`, the current branch and
its merge-base with the default branch, an open PR if the user mentions one).
Offer, with the detected default first and its size:

- Current changes: uncommitted changes plus the branch's commits since the
  merge-base ("12 files, +340/-80").
- Specific paths: files or folders, reviewed in full.
- A PR or commit range.
- The whole repository: warn that it is slow and expensive, and that
  reviewers will prioritise by risk rather than read everything.

If the user's request already makes the scope obvious (a path, "this PR"),
do not ask about it.

**Themes.** Offer the four groups from the table as a multiple choice where
several can be picked, plus "all". Recommend a selection based on the scope
and say why (for example: a docs-only change does not need Performance; a
change to auth code should include Correctness). The user can also name
individual themes.

## 2. Prepare the review package

- Collect the list of files in scope and, for diff scopes, write the unified
  diff to a temporary file so every reviewer reads the same thing without
  pasting it into prompts.
- Find guidance files: `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`,
  convention docs, linter configs, including ones in subfolders that apply
  to files in scope.
- Find out what the change is for if it is not obvious: commit messages, the
  PR description, a plan folder that references it.
- Very large scopes: if a diff is huge or the repository is large, split the
  files into a few coherent areas and give each reviewer one area, rather
  than asking one reviewer to read everything.

## 3. Review

Launch one reviewer subagent per selected theme, all in parallel, with
`references/reviewer-brief.md` and the full content of the theme's file. Each
reviewer sees only its own theme. Do not tell reviewers what to ignore beyond
what the brief and theme already say; pre-judging findings hides real
problems.

## 4. Validate

1. Merge the reports. Remove duplicates (same location and same underlying
   problem, often found by two themes); keep the clearest description and
   list both themes.
2. Send the findings to validator subagents with `references/validator.md`,
   up to about ten findings each, grouped by file or area. A validator must
   not be the reviewer that produced the finding.
3. Drop `REJECTED` findings. Keep `CONFIRMED` and `PLAUSIBLE`, with the
   validator's severity.
4. Skim the rejections: if a validator rejected something that looks serious,
   check it yourself before dropping it.

## 5. Report

Present the report in chat, in the user's language:

```
## Review: <scope>
Themes: <run> · skipped: <themes and why>
Findings: <n> critical · <n> high · <n> medium · <n> low  (<n> discarded by validation)

### 1. <title>  — critical · bugs · confirmed
<path:line>
<what is wrong and the concrete impact>
Fix: <specific change>

### 2. ...

### Not covered
<what reviewers reported they could not review>
```

- Order by severity, then confidence. `PLAUSIBLE` findings say what would
  confirm them.
- Mark `pre-existing` findings so they are not mistaken for regressions.
- If there are no findings, say so plainly, with the themes and scope that
  were covered. Do not invent minor findings to fill the report.

Then offer:

- to fix some or all findings (the user picks which);
- to save the report as a Markdown file; if the review relates to a plan
  folder, save it there as `review-<YYYY-MM-DD>.md`;
- to capture findings that will not be fixed now as tickets (`new-ticket`).

## Subagents

Launch subagents with your harness's task tool, using its general-purpose
agent (`general-purpose` in Claude Code, `general` in opencode). Each one
starts with no context: the brief is all it knows. If the harness lets you
choose models, use a capable one for the bugs and security reviewers and for
validation. If no subagents are available, review one theme at a time
yourself, and validate in a separate pass that re-reads the code instead of
trusting your earlier notes.

## Red flags

- Reporting findings that were not validated.
- A finding without a location or without a concrete impact.
- Padding the report with style nits when the real result is "no problems".
- Fixing code during the review without the user asking.
