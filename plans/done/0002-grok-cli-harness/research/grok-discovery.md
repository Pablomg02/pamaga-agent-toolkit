# Where Grok CLI looks for skills, agents and commands

Checked on 2026-10-04 against Grok CLI `1.0.46 (2765805b9442) [stable]`
installed in `~/.grok/` (binary `~/.grok/bin/grok`). Sources: the docs the CLI
ships locally (`~/.grok/README.md`, `~/.grok/docs/user-guide/08-skills.md`,
`05-configuration.md`, `16-subagents.md`, `10-hooks.md`) and experiments with
`grok inspect --json` and a fake `HOME`.

## Documented

Skills (`08-skills.md`, "Skill Locations"):

| Location | Scope |
| --- | --- |
| `./.grok/skills/`, `./.grok/commands/` | local (cwd), highest priority |
| `<repo_root>/.grok/skills/`, `.../commands/` | repo |
| `~/.grok/skills/`, `~/.grok/commands/` | user |
| `~/.claude/skills/`, `~/.claude/commands/` | user, Claude compatibility (configurable) |
| `./.claude/skills/`, `./.claude/commands/` | local / repo |
| `~/.cursor/skills/`, `./.cursor/skills/` | Cursor compatibility |

- "Grok deduplicates skills by name -- a higher-priority location overrides a
  lower one. Grok also scans `.agents/skills/` (and `commands/`) at each tier."
- "Flat `*.md` files under a `commands/` directory become user-invocable
  slash commands (filename stem = command name)."
- Every skill is a slash command `/<name>`; `user-invocable: false` hides it.
- Reading the Claude dirs can be turned off with `[compat.claude] skills =
  false` in `~/.grok/config.toml` or `GROK_CLAUDE_SKILLS_ENABLED=false`
  (`05-configuration.md`, "Harness compatibility"; default `true`).
- Project skills, rules, hooks and MCP load only in a trusted folder
  (`/hooks-trust` or `--trust`; store `~/.grok/trusted_folders.toml`).
- Agents: `.grok/agents/`, `~/.grok/agents/`, plus `.claude/agents/` and
  `~/.claude/agents/` (README, "Claude Code Compatibility"). An agent is a
  `.md` file with `name` and `description` frontmatter: the toolkit's
  `agents/<name>.md` format.
- Grok also reloads skills when the files change on disk.

## Observed (fake HOME, `grok inspect --json`)

User scope, one skill `dup` in `~/.grok/skills`, `~/.claude/skills` and
`~/.agents/skills`, plus one skill alone in each of `~/.agents/skills`,
`~/.config/opencode/skills`, `~/.gemini/config/skills`, `~/.gemini/skills`
and `~/.codex/skills`:

- `dup` listed once, from `~/.grok/skills`.
- `only-agents` listed (from `~/.agents/skills`).
- Not listed: the opencode, `~/.gemini/config`, `~/.gemini` and `~/.codex`
  ones.
- A `~/.grok/commands/dup.md` was hidden by the `dup` skill (same name).

Project scope (`GROK_FOLDER_TRUST=0`, a git repo with skills in
`.agents/skills`, `.opencode/skills`, `.claude/skills` and a
`.grok/commands/proj-cmd.md`):

- Listed: `.agents/skills/proj-agents`, `.claude/skills/dup` (overriding the
  user one), `.grok/commands/proj-cmd` as a skill.
- Not listed: `.opencode/skills`.
- Without folder trust, no project skill was listed at all.

Agents: `myagent` in both `~/.grok/agents` and `~/.claude/agents` listed once,
from `~/.grok/agents`; `~/.claude/agents/claudeagent.md` listed;
`~/.agents/agents/agx.md` not listed.

On the real machine `grok inspect` lists the 12 toolkit skills from
`~/.claude/skills`, which is why Grok "already sees" them. None of the
toolkit's names collide with Grok's bundled skills (`code-review`, `review`,
`implement`, `execute-plan`, ...).

## Consequences for the installer

- Grok is to `~/.claude/skills` what opencode is: a reader of Claude's dir at
  both scopes, and of `.agents/skills` (the Antigravity project dir) in a
  project. At user scope Antigravity uses `~/.gemini/config`, which Grok does
  not read.
- Command wrappers must not go to Grok: `commands/<name>.md` would become a
  skill with the same name as the real one.
- Agents can go to `~/.grok/agents` in the usual format; a duplicate in
  `~/.claude/agents` is harmless because Grok deduplicates agents by name.
- The Claude compatibility switch can remove `claude` as a provider.
