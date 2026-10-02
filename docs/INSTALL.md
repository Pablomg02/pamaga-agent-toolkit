# Manual installation

Everything in this repository is plain Markdown, so installing it means putting
the files where your coding agent looks for them. There are two ways to do that:
copy the files, or symlink them. The install script does the symlinking for you,
but doing it by hand is just as easy.

## Repository layout

```
skills/<name>/SKILL.md   # one folder per skill
agents/<name>.md         # subagents
commands/<name>.md       # slash commands
```

## Where each agent looks

| Agent | Skills | Subagents | Commands |
| --- | --- | --- | --- |
| opencode | `~/.config/opencode/skills/<name>/SKILL.md` | `~/.config/opencode/agents/<name>.md` | `~/.config/opencode/commands/<name>.md` |
| Claude Code | `~/.claude/skills/<name>/SKILL.md` | `~/.claude/agents/<name>.md` | `~/.claude/commands/<name>.md` |

Notes:

- opencode also reads skills from `~/.claude/skills/`, so skills installed for
  Claude Code are picked up there too.
- Both agents also support project-scoped installs: `.opencode/` and `.claude/`
  inside a repository. This guide covers the global (user) scope.

## Option 1: symlinks (recommended)

Symlinks keep this repository as the single source of truth: after `git pull`,
your agents use the new content immediately.

```bash
REPO="$HOME/GitHub/pamaga-agent-toolkit"
DEST="$HOME/.config/opencode"   # opencode; use $HOME/.claude for Claude Code

mkdir -p "$DEST"/{skills,agents,commands}
ln -sfn "$REPO"/skills/*/     "$DEST/skills/"
ln -sfn "$REPO"/agents/*.md   "$DEST/agents/"
ln -sfn "$REPO"/commands/*.md "$DEST/commands/"
```

The `ln` commands rely on shell globs, so they only link entries that already
exist: add content to this repository first, or run the commands again later.

## Option 2: copy the files

Use this if you prefer real files, for example to edit them per machine.

```bash
REPO="$HOME/GitHub/pamaga-agent-toolkit"
DEST="$HOME/.config/opencode"   # opencode; use $HOME/.claude for Claude Code

mkdir -p "$DEST"/{skills,agents,commands}
cp -R "$REPO"/skills/*/     "$DEST/skills/"
cp    "$REPO"/agents/*.md   "$DEST/agents/"
cp    "$REPO"/commands/*.md "$DEST/commands/"
```

Note that copied files do not update on `git pull`; re-run the copy after
pulling.

## Option 3: the install script

The script automates the symlink approach above:

```bash
./scripts/install.sh opencode   # default
./scripts/install.sh claude
./scripts/install.sh all
./scripts/install.sh --uninstall all
```

It only creates or removes symlinks that point into this repository, so it never
touches other files in your config directories.

## Per-agent notes

### opencode

Restart opencode after installing. Ask the agent to list its available skills,
or type `/` to see the commands.

### Claude Code

Restart Claude Code after installing. Skills are listed in `/help` and subagents
in `/agents`.

## Updating and uninstalling

- Symlink installs: just run `git pull`.
- Copy installs: `git pull`, then re-run the copy commands.
- Uninstall: run `./scripts/install.sh --uninstall <target>`, or delete the
  symlinks or files you created.
