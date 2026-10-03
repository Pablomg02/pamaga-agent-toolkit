---
name: plan-page
description: Generate plan.html, a self-contained explainer page (one HTML file, fixed house style, no external resources) for a plan, roadmap or ticket folder - why, approach, decisions, execution mode and order, tasks, acceptance criteria, risks and progress. Use only when the user explicitly asks for a page, web page, HTML or visual summary of a plan, or to regenerate an outdated one. Never as a side effect of planning or implementing.
---

# Plan explainer page

Turn a plan folder into `plan.html`: a page someone can open in a browser and
understand in five minutes, without knowing the codebase. Every page uses the
same style, so the user recognises them at a glance; you write the content,
not the design.

Load the `plans-convention` skill first. `<plans-convention>` below stands
for the folder that skill was loaded from.

## When

Only when the user asks for it. Do not generate a page as a side effect of
planning or implementing.

When some other work changes a `plan.md` whose folder already has a page, the
page goes out of date. The rule, defined in `plans-convention`, is: say so and
offer to regenerate; never regenerate silently. If the user asks for a page
and one exists, check `plans.py page-status <id>`: if it is `fresh`, tell
them and ask whether they still want it rebuilt.

## Steps

1. **Find the folder**: `plans.py find <id>`. Note its status from the
   folder it sits in (`backlog`, `in-progress`, `done`).
2. **Read the sources**: `plan.md` in full, plus `plan-review.md` and the
   `research/` notes it links when they help explain a decision. For a
   roadmap, also read the `plan.md` of each derived plan that exists, to show
   their real status.
3. **Write the page**: copy `assets/template.html` to `<folder>/plan.html`
   and replace the example content with this plan's (rules below).
4. **Stamp it**: `plans.py stamp-page <id>`. This records the hash of the
   `plan.md` the page was built from, which is how staleness is detected
   later. It also reports any external reference; remove them and stamp
   again. (A code sample that mentions `src=` in escaped text can trigger a
   false alarm; check the reported snippet.)
5. **Report** the path to the user. Offer to open it if the harness can.

## Writing the content

- **Explain, do not copy.** The plan is written for an implementer; the page
  is for a reader. Lead with what changes for users and why, in plain
  sentences. Keep the technical detail in the task cards.
- **Lede**: two or three sentences that a newcomer understands.
- **Stats**: three or four numbers that matter for this plan (tasks, done,
  risks, open questions; milestones and derived plans for a roadmap).
- **Execution order**: the intro sentence states the plan's *Execution*
  mode: "One agent works through the tasks in order", or the subagent
  packages, which tasks each one holds and why the work was split. Then
  compute the waves from each task's *Depends on*: wave 1 holds tasks with
  no dependencies, wave N those whose dependencies are all in earlier waves.
  With subagents, name each task's package in its chip (`P1 · after T1`).
  If there is only one wave, a sentence saying the tasks are independent
  replaces the component.
- **Status**: take task and criteria status from the *Implementation* ledger.
  Before implementation starts, every task is pending and the *Progress*
  section is omitted.
- **Roadmaps**: use the *Milestones* and *Derived plans* components instead
  of *Execution order* and *Tasks*.
- **Tickets**: keep it short: *Why*, the acceptance criteria and, if the work
  has started, *Progress*.
- Omit sections that would be empty, and their table-of-contents links.
- Never add information that is not in the plan folder. If something a reader
  would need is missing from the plan, mention it to the user instead of
  inventing it.
- Write in English.

## Style rules

- Do not modify the `<style>` block or the inline print script. Use only the
  components marked `COMPONENT` in the template; repeat or remove them as
  needed.
- The file must be self-contained: no external stylesheets, scripts, fonts,
  images or iframes. Small images from the plan folder, if really needed, go
  inline as `data:` URIs.
- Escape `&`, `<` and `>` in all text taken from the plan.
- Paths and commands go in `<code>` or `.path` elements.
- Check the result: it is valid HTML, every table-of-contents link points to
  an existing section, and nothing from the example content remains.
