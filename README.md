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

### Planning and implementation

These skills share one convention: every piece of work is a folder under
`plans/` (`backlog/`, `in-progress/`, `done/`) with a canonical `plan.md`.

| Skill | What it does |
| --- | --- |
| `plans-convention` | Defines the `plans/` layout and `plan.md` format, with a script for ids, moves and validation. Loaded by the others. |
| `make-roadmap` | Writes a long-term over-plan: milestones, ordering, and the plans that should derive from it. |
| `make-plan` | Investigates with helper subagents, asks until nothing is ambiguous, writes the plan, and has two independent critics challenge it. |
| `implement-plan` | Coordinates one implementer subagent per task and an independent verifier that checks the real result, with bounded retries. |
| `new-ticket` | Captures a bug, idea or follow-up in the backlog in a minute. |
| `plan-page` | Generates a self-contained HTML page that explains a plan, stored in its folder. |

```
idea ──► make-roadmap ──► make-plan ──► implement-plan ──► deep-review
  │        (optional)        ▲   │            │
  └──► new-ticket ───────────┘   └─ plan-page └─► follow-ups ──► new-ticket
```

### Quality

| Skill | What it does |
| --- | --- |
| `deep-review` | Asks what to review, runs one reviewer subagent per theme (bugs, security, performance, tests, simplification, conventions, docs quality, outdated docs), and validates every finding before reporting. |
| `find-bug` | Systematic debugging: reproduce, narrow down, root cause, fix with a regression test. |

### Working in parallel

| Skill | What it does |
| --- | --- |
| `concurrent-work` | Several agents on one repository: each works on its own branch and git worktree, and a shared board (`.git/agent-work/`) shows who is doing what, flags overlapping paths and stale sessions, and keeps branches integrating early. |

In Claude Code every skill is also a slash command (`/make-plan`); in
opencode the wrappers in `commands/` provide the same.

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
