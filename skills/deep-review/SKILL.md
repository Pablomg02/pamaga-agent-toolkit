---
name: deep-review
description: Code review at the depth the change deserves - a quick review by the agent itself, one generalist reviewer subagent, or one reviewer per theme (bugs, security, performance, tests, simplification, conventions, design, documentation) with independent validators. Picks the themes from what actually changed, asks the user for the depth when the change is not trivial, and reports only findings that survived a check. Use when the user asks for a code review, audit or second opinion of changes, a branch, a PR, a folder or the whole repository, or asks to look for bugs, optimisations or outdated docs in existing code. Not for debugging a known failure (find-bug) or reviewing a plan.
---

# Deep review

Review as deeply as the change deserves, and no deeper. A typo fix does not
need five subagents; a change to authentication code does. Whatever the
depth, every finding is checked against the code before the user sees it,
so the report only contains problems that survived an attempt to disprove
them.

This skill reports; it does not change code. Offer fixes at the end.

## Themes

| Theme | File | Applies when the scope contains |
| --- | --- | --- |
| Bugs and logic errors | `references/themes/bugs.md` | Code |
| Security | `references/themes/security.md` | Code that handles input, auth, secrets, files, network or data |
| Tests | `references/themes/tests.md` | Code or tests |
| Performance and optimisation | `references/themes/performance.md` | Code on a hot path, loops over data, queries, I/O |
| Simplification and maintainability | `references/themes/simplification.md` | Code |
| Project conventions | `references/themes/conventions.md` | Anything the project has written rules for |
| Design and decisions | `references/themes/design.md` | New modules, interfaces, architecture, or work from a plan |
| Documentation quality | `references/themes/docs-quality.md` | Documentation |
| Outdated documentation | `references/themes/docs-outdated.md` | Code whose behaviour is documented, or documentation |

Only themes that apply to what is in scope are candidates: pure code changes
do not get the documentation themes, a docs-only change does not get
Performance or Security, and a small fix does not get Design. The user can
always add a theme, or a concern of their own ("check the error messages are
consistent"); treat that as one more theme with their words as its file.

## Depth

| Depth | How | Validation |
| --- | --- | --- |
| **Quick** | You review it yourself, theme by theme. | A second pass of your own: re-read the code at every finding and try to disprove it. |
| **Generalist** | One reviewer subagent with all the candidate themes, so the review gets fresh eyes. | You validate its findings yourself, re-reading the code. |
| **By theme** | One reviewer subagent per selected theme, in parallel. | Validator subagents, as in step 4. |

## 1. Decide what to review

Three things must be clear before reviewing: the **scope**, the **depth**
and, for a review by theme, the **themes**. Take whatever the user already
said ("quick review of src/api", "review this branch for security") and ask
only for what is missing, in one round, using the harness's question tool if
it has one.

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

**Depth.** Look at what is in scope and pick the candidate themes.

- Small and of one kind (a few files of prose, a small fix, a config
  tweak): do a **quick** review without asking; say so in one line, so the
  user can ask for more.
- Anything bigger or mixed (code plus docs, new interfaces, several
  modules, risky areas): ask for the depth, with your recommendation first
  and why. Usually **generalist**; recommend **by theme** for risky code
  (auth, payments, data migrations, concurrency) or a release.

**Themes** (by theme only). Let the user pick from the candidate themes with
multiple-choice questions where several options can be selected (at most
four options per question; group them as code themes and maintainability
and docs themes when there are more). Mark the ones you recommend with
"(recommended)" and say why in their description. Each selected theme is
one reviewer, so fewer themes means a faster, cheaper review. If the user
selects nothing, ask whether to cancel instead of guessing.

Without a question tool, ask in chat as a numbered list, recommended options
marked, and let the user answer with numbers.

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

- **Quick**: review the scope yourself, one theme at a time, following each
  theme's file and the rules of `references/reviewer-brief.md` (evidence,
  concrete impact, no style nits).
- **Generalist**: launch one reviewer subagent with
  `references/reviewer-brief.md` and the content of every candidate theme
  file, one after another under *Your theme*.
- **By theme**: launch one reviewer subagent per selected theme, all in
  parallel, with `references/reviewer-brief.md` and the full content of that
  theme's file. Each reviewer sees only its own theme.

**Work from a plan**, at any depth: also check its claims yourself. Re-run
the commands of the plan's *Verification* section and of the acceptance
criteria marked done, and compare the *Implementation* ledger with the diff.
A criterion marked done whose command fails, or a ledger entry the diff does
not back, is a finding (high, or critical if it hides broken behaviour).
This is cheap and catches an implementer that reported evidence it did not
produce.

Do not tell reviewers what to ignore beyond what the brief and themes
already say; pre-judging findings hides real problems.

## 4. Validate

1. Merge the findings. Remove duplicates (same location and same underlying
   problem, often found by two themes); keep the clearest description and
   list both themes.
2. Check every finding, following `references/validator.md`:
   - **Quick** and **generalist**: do it yourself, as a separate pass that
     re-reads the code at each location instead of trusting the first read.
   - **By theme**: send the findings to validator subagents, up to about ten
     each, grouped by file or area. A validator must not be the reviewer
     that produced the finding.
3. Drop `REJECTED` findings. Keep `CONFIRMED` and `PLAUSIBLE`, with the
   corrected severity.
4. Skim the rejections: if a validator rejected something that looks
   serious, check it yourself before dropping it.

## 5. Report

Present the report in chat, in the user's language:

```
## Review: <scope>
Depth: <quick | generalist | by theme> · themes: <run> · skipped: <themes and why>
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
choose models, use a capable one for reviewers and validators. If no
subagents are available, offer only the quick depth, and validate in a
separate pass that re-reads the code instead of trusting your earlier notes.

## Red flags

- Reporting findings that were not validated.
- Offering themes that do not apply to what changed (Design for a typo,
  Performance for prose).
- Launching subagents for a small change without the user asking.
- A finding without a location or without a concrete impact.
- Padding the report with style nits when the real result is "no problems".
- Fixing code during the review without the user asking.
