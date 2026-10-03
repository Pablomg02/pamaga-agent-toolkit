---
name: make-roadmap
description: Write a long-term roadmap (an over-plan) as a plan folder - vision, milestones with exit criteria, ordering and dependencies, and the smaller implementation plans that should derive from it and what each one resolves. Only writes the roadmap; it never creates or runs the derived plans. Use when the user describes something to achieve over weeks or months, too big for one plan, or asks for a roadmap, a long-term plan, phases, milestones or "how do we get from here to there".
---

# Make a roadmap

A roadmap answers *what has to be true, in what order, and which plans will
get us there*. It does not answer *how* each part is built: that is the job of
the derived plans, each written later with `make-plan` when the user decides
to start it. Keeping the roadmap at that altitude is what lets it survive
changes: a milestone stays valid while the plans beneath it are rewritten.

This skill only writes the roadmap. It does not create derived plan folders,
does not call `make-plan`, and does not implement anything.

Load the `plans-convention` skill first. `<plans-convention>` below stands
for the folder that skill was loaded from.

## 1. Understand the destination

Establish with the user, asking only what you cannot find out yourself:

- the long-term outcome and why it matters now;
- how they will know it has been reached (observable success criteria);
- the horizon and the constraints: deadlines, team, budget, technologies
  that are fixed or forbidden;
- what is explicitly out of scope.

Read enough of the repository and existing `plans/` to describe the current
state accurately and to avoid duplicating plans that already exist. A roadmap
built on a wrong picture of the present is wrong everywhere.

Ask in batches (up to four questions at a time, recommended option first),
using the harness's question tool if it has one. Loop until the outcome,
constraints and scope are clear.

## 2. Shape the milestones

- A milestone is an **observable state** of the system or product ("users can
  sign in with SSO in production"), not an activity ("work on SSO").
- Each milestone has exit criteria someone can check.
- Each milestone should deliver value or remove a major risk on its own, so
  the roadmap is useful even if it stops halfway.
- Put the riskiest unknowns early. If something is too uncertain to plan,
  make the first derived plan a spike whose result is a decision.
- Prefer three to seven milestones. More usually means they are plans in
  disguise.

## 3. Derive the plans

For each milestone, list the implementation plans it needs. For each one:

- a working title and the specific question or deliverable it resolves;
- the milestone it serves;
- what it depends on (other derived plans, external events);
- a rough size (small / medium / large) when it helps ordering.

A derived plan should be something `make-plan` can turn into tasks in one
sitting: one coherent deliverable, days to a couple of weeks of work. Split
anything bigger.

Plans that already exist in `plans/` and fit the roadmap are listed with
their id instead of as new rows.

## 4. Order and dependencies

Explain the order in *Ordering and dependencies*: what unblocks what, what
can run in parallel, and the critical path. Check that the dependencies have
no cycles. Record risks with a mitigation, and anything still undecided under
*Open questions* with when it must be decided by.

## 5. Write it

1. `python3 <plans-convention>/scripts/plans.py new --type roadmap --title "<title>"`.
2. Fill `plan.md` from the roadmap template. In *Derived plans*, the `Plan`
   column is `—` and the status `not started` for plans that do not exist yet.
3. Run `plans.py validate`.

## 6. Hand off

Report to the user: roadmap id and path, the milestones in one line each, and
the derived plans in recommended order. Tell them that each derived plan is
created on demand with `make-plan` (which links it to this roadmap with
`--parent`) and implemented with `implement-plan`. Stop there.

## Keeping it alive

When you later touch a roadmap (a derived plan is created, started or closed,
or the user changes direction), update its *Derived plans* table, add a dated
line to its *Implementation* log, and follow the generated page rule in
`plans-convention`. Close the roadmap in `done/` when its success criteria
are met or it is abandoned, with *Results* per milestone.

## Red flags

- Tasks, file paths or code in the roadmap: that detail belongs in the
  derived plans.
- Milestones that cannot be checked, or that only make sense together.
- Creating derived plan folders, or starting `make-plan`, without the user
  asking.
- Planning the present from assumptions instead of reading the repository.
