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

They are intentionally model-agnostic: plain Markdown instructions with no
harness-specific magic, so the same skill works with Claude, DeepSeek, GPT, or
whatever model a given agent is running.

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
Restart your agent after installing.

## Manual installation

Installing by hand is trivial — it is just copying Markdown files (or symlinking
them) into the right directories. See the
[installation guide](docs/INSTALL.md) for the exact locations and commands for
each agent.
