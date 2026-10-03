---
name: plans-convention
description: Where plans, roadmaps and tickets live in a repository and how they are named, structured and moved - plans/ with backlog/, in-progress/ and done/, one <id>-<slug>/ folder per item with a canonical plan.md, and a bundled script for ids, moves and validation. Load it before creating, finding, updating, moving or closing a plan, roadmap or ticket, and whenever the user mentions plans/, the backlog, a plan id ("plan 0042") or the status of planned work.
---

# Plans convention

Every piece of planned work in a repository is a folder. The folder holds a
canonical `plan.md` and any artifact the work produces. Where the folder sits
is its status. This keeps plans greppable, reviewable in pull requests, and
readable by any person or agent without special tools.

## Layout

```
plans/
├── backlog/        # accepted but not started
├── in-progress/    # being implemented
└── done/           # closed: finished, partially finished or abandoned
    └── 0007-add-login/
        ├── plan.md         # canonical document, always present
        ├── plan.html       # optional explainer page (plan-page skill)
        ├── plan-review.md  # optional: critiques and how they were handled
        └── research/       # optional: notes, references, images
```

- `plans/` lives at the repository root. Only the three status folders and an
  optional `README.md` belong directly inside it.
- Folder name: `<id>-<slug>`. The id is a zero-padded sequential number of at
  least four digits (`0007`). The slug is lowercase words joined by single
  hyphens, short and descriptive (`add-login`, not `task`).
- Ids are global across the three folders and across types. They are never
  reused and never changed, even if a plan is abandoned, because other plans,
  commits and conversations refer to them.

## Types

All three share the folder layout and the five sections below. The `type`
field in the frontmatter says which one a folder is.

| Type | Use it for | Created by |
| --- | --- | --- |
| `plan` | An implementable change, broken into tasks with acceptance criteria. | `make-plan` |
| `roadmap` | A long-term over-plan: milestones, ordering, and the plans that derive from it. Never implemented directly. | `make-roadmap` |
| `ticket` | A bug, idea or request captured quickly; becomes a plan when it needs more than a few steps. | `new-ticket` |

A plan that derives from a roadmap sets `parent: "<roadmap id>"`, and the
roadmap lists it by id in its *Derived plans* table. References between
folders always use the id (`see 0012`), never the path, because paths change
when folders move.

## plan.md

```markdown
---
id: "0007"
title: "Add login"
type: plan            # plan | roadmap | ticket
created: 2026-10-03
parent: "0003"        # optional: the roadmap this derives from
---

# 0007 — Add login

## Justification    why the work exists, goals and non-goals
## Plan             context, approach, decisions, tasks, verification, risks
## Implementation   filled while implementing: git policy, ledger, deviations
## Results          what was delivered, with evidence
## Closure          date, outcome, follow-ups by id
```

The full skeletons are `templates/plan.md`, `templates/roadmap.md` and
`templates/ticket.md`. Always start from them through the script, never from
memory, so every folder has the same shape. The status is not stored in the frontmatter:
the folder is the only source of truth.

Write plans, roadmaps, tickets and generated pages in English.

## Status transitions

- `backlog → in-progress` when implementation starts.
- `in-progress → done` when the work is closed, after the *Results* and
  *Closure* sections are written. A plan abandoned halfway also goes to
  `done`, with the outcome stated in *Closure*.
- Moving back (`done → in-progress`) is allowed when a plan is reopened; note
  why in *Implementation*.

Move folders with the script, never by hand, so ids stay consistent.

## The script

`scripts/plans.py` (Python 3.9+, standard library only) is relative to this
file. Run it from anywhere inside the repository; it finds `plans/` at the
repository root (override with `--plans-dir`). Plans are referenced by id
(`42` or `0042`) or by folder path.

```bash
python3 scripts/plans.py next-id                      # next free id
python3 scripts/plans.py check-id 0042                # exit 0 free, 1 used
python3 scripts/plans.py new --title "Add login" [--type plan|roadmap|ticket] [--slug add-login] [--parent 0003]
python3 scripts/plans.py find 42                      # print the folder path
python3 scripts/plans.py move 42 in-progress          # change status
python3 scripts/plans.py list [--status backlog] [--type roadmap]
python3 scripts/plans.py validate                     # layout, ids, frontmatter, stale pages
python3 scripts/plans.py page-status 42               # plan.html: missing | fresh | stale
python3 scripts/plans.py stamp-page 42                # record plan.md hash in plan.html
```

`new` creates the folder in `backlog/` with the next free id and prints its
path. Ids already used in other local branches and git worktrees count as
taken, so parallel work does not pick the same id. Run `validate` after any
manual change to `plans/`; it also spots duplicated ids after a merge.

## Generated page

A plan folder may contain `plan.html`, an explainer page generated by the
`plan-page` skill. The page records a hash of the `plan.md` it was built from.

**Generated page rule.** When you finish a piece of work that changed a
`plan.md` whose folder has a `plan.html`, run `page-status` once. If it is
`stale`, tell the user that the page no longer matches the plan and offer to
regenerate it. Check at the end, not after each edit: implementation updates
the ledger after every task, and one reminder is enough. Never regenerate the
page without being asked: the user decides whether it is worth refreshing.

## Rules

- One folder per plan, roadmap or ticket. Large efforts are a roadmap plus
  several plans, not one giant plan with sub-folders.
- Keep everything about the work inside its folder: research notes, review
  logs, images, generated pages. Nothing about a plan lives elsewhere.
- Do not delete plan folders. Abandoned work is closed in `done/` with the
  reason, so the history explains itself.
- Do not rename a folder's id. Renaming the slug is allowed only before the
  plan is referenced anywhere else.
