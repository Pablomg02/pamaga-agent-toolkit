<p align="center">
  <img src="images/banner.webp" alt="PAMAGA Agent Toolkit — Macaco giving macacos instructions" width="100%">
</p>

# pamaga-agent-toolkit

A collection of agent skills, subagents and commands for opencode and
Claude Code.

## Philosophy

Most of what lives here is not about *what* the agent should do, but *how* I
want it done. These are the instructions and workflows I kept typing over and
over — the same request, phrased the same way, because it consistently got me
the result I wanted.

Writing them down means:

- I no longer re-explain the same thing every session.
- The behavior stays consistent across projects and conversations.
- When I find a better way to do something, I improve the skill here and the
  change applies everywhere from then on.

Above all, simplicity is the point. These skills are not meant to box the
agent in with rigid restrictions — they only nudge it toward a few basic
organizational patterns that make the work easier. When an instruction closes
off too many options or adds ceremony without value, it does not belong here.

They are intentionally model-agnostic: plain Markdown instructions with no
harness-specific magic, so the same skill works with Claude, DeepSeek, GPT, or
whatever model a given agent is running.

## What's inside

Ten skills that cover the life of a change, from the first question to the
pull request. You do not need to remember them: each one loads on its own
when your request matches ("plan the CSV export", "ship it"), and each one is
also a slash command (`/make-plan`). The table follows the diagram, stage by
stage.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/workflow-dark.svg">
    <img src="images/workflow-light.svg" alt="Workflow: research-topic and new-ticket feed make-roadmap and make-plan; make-plan, implement-plan, deep-review and ship-work are the main flow; plan-page, find-bug and save-learning plug in." width="100%">
  </picture>
</p>

| Skill | Use it when | You get |
| --- | --- | --- |
| [`research‑topic`](skills/research-topic/SKILL.md) | You need an answer before deciding: "can we use X?", "how does Y work here?" | An answer backed by code and sources. Single or multi agent, as you choose; saved only if you ask. |
| [`make‑roadmap`](skills/make-roadmap/SKILL.md) | The goal takes weeks or months. | A roadmap: milestones with exit criteria and the plans to derive from them. |
| [`make‑plan`](skills/make-plan/SKILL.md) | A feature, refactor or non-trivial fix needs designing before coding. | A `plan.md` with tasks and verifiable criteria, after your questions are answered and two independent critics have challenged it. |
| [`new‑ticket`](skills/new-ticket/SKILL.md) | Something should be done, but not now. | A ticket in the backlog, in a minute. |
| [`plan‑page`](skills/plan-page/SKILL.md) | You want to read or share a plan at a glance. | A self-contained `plan.html` in the plan's folder. |
| [`implement‑plan`](skills/implement-plan/SKILL.md) | A plan is ready. | The code, built by subagents in small waves and checked by an independent verifier, with progress logged in the plan. |
| [`find‑bug`](skills/find-bug/SKILL.md) | Something fails and the cause is not obvious. | The root cause, a fix, and a regression test. |
| [`deep‑review`](skills/deep-review/SKILL.md) | Before merging, or to audit existing code. | Findings from one reviewer per theme (bugs, security, tests…), each confirmed by a validator. |
| [`ship‑work`](skills/ship-work/SKILL.md) | The work is done. | Commits, and if you want, a push and a pull request. You choose how far. |
| [`save‑learning`](skills/save-learning/SKILL.md) | You learned something worth remembering. | A short note in `docs/learnings/` that cites the plan it came from. |

Everything the skills write lives in your repository, as plain Markdown:

```
plans/
├── backlog/        plans, roadmaps and tickets not started yet
├── in-progress/    being implemented
└── done/           closed, with results
docs/
├── research/       saved research-topic reports
└── learnings/      save-learning notes
```

A plan's folder holds everything about it: `plan.md`, research, critique,
page. The layout is defined by `plans-convention`, a supporting skill the
others load on their own; it has no command.

## Quick install

```bash
git clone https://github.com/Pablomg02/pamaga-agent-toolkit.git
cd pamaga-agent-toolkit

./scripts/install.sh opencode   # opencode (default)
./scripts/install.sh claude     # Claude Code
./scripts/install.sh all        # both
```

The script creates individual symlinks into each agent's config directory, so
`git pull` updates everything in place. It requires bash (Linux, macOS or WSL).
Some skills bundle small Python 3.9+ scripts (standard library only), so
`python3` must be available. Restart your agent after installing.

## Manual installation

Installing by hand is trivial — it is just copying Markdown files (or symlinking
them) into the right directories. See the
[installation guide](docs/INSTALL.md) for the exact locations and commands for
each agent.

## Development

Conventions for writing skills, commands and agents are in
[docs/CONVENTIONS.md](docs/CONVENTIONS.md). Before committing:

```bash
python3 scripts/validate.py              # --fix regenerates opencode wrappers
python3 -m unittest discover -s tests
```

Each skill has behaviour and trigger cases in [evals/](evals/README.md).
The workflow diagram is generated: after adding or renaming a skill, update
`scripts/draw_workflow.py` and run it (a test fails while it is outdated).

Every push to `main` that passes CI is released as `YYYY.MM.DD.N` (date in
Spain, daily counter); see [Releases](https://github.com/Pablomg02/pamaga-agent-toolkit/releases).
