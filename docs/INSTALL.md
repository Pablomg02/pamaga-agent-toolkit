# Manual installation

Everything in this repository is plain Markdown, so installing it means putting
the files where your coding agent looks for them. There are two ways to do that:
copy the files, or symlink them. The install script does the symlinking for you,
but doing it by hand is just as easy.

## Repository layout

```
skills/<name>/SKILL.md   # one folder per skill, with its bundled files
agents/<name>.md         # subagents
commands/<name>.md       # opencode wrappers so each skill is also /<name>
```

Skills that bundle scripts need Python 3.9 or newer (`python3`). They use the
standard library only.

## Where each agent looks

| Agent | Skills | Subagents | Commands |
| --- | --- | --- | --- |
| opencode | `~/.config/opencode/skills/<name>/SKILL.md` | `~/.config/opencode/agents/<name>.md` | `~/.config/opencode/commands/<name>.md` |
| Claude Code | `~/.claude/skills/<name>/SKILL.md` | `~/.claude/agents/<name>.md` | not needed |

Notes:

- opencode also reads skills from `~/.claude/skills/`, so skills installed for
  Claude Code are picked up there too.
- Claude Code registers every skill as `/<name>` on its own. Do not install
  `commands/` there: the wrappers would collide with the skills.
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
ln -sfn "$REPO"/commands/*.md "$DEST/commands/"   # opencode only
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
cp    "$REPO"/commands/*.md "$DEST/commands/"   # opencode only
```

Note that copied files do not update on `git pull`; re-run the copy after
pulling.

## Option 3: the install script

The script keeps the symlink approach above, now backed by an installer with a
full-screen terminal UI:

```bash
./scripts/install.sh          # interactive: pick harnesses, skills, mode
./scripts/install.sh opencode # non-interactive, the arguments from before
./scripts/install.sh claude
./scripts/install.sh all
./scripts/install.sh --uninstall all
```

With no arguments in an interactive terminal, `./scripts/install.sh` opens the
TUI: choose harnesses, components and mode (`link` or `copy`), review the
actions and apply them. Space marks, the right arrow (or `Enter`) advances,
the left arrow (or `Esc`) goes back, `Enter` on the review applies, `i`
opens the details of a skill and `?` lists the keys.

The same engine has a non-interactive CLI, useful in scripts and CI:

```bash
python3 scripts/install.py --yes --harness all --offline   # install everything
python3 scripts/install.py --update                        # update what is installed
python3 scripts/install.py --update --pull                 # git pull first, then update
python3 scripts/install.py --status                        # what is installed where
python3 scripts/install.py --status --json                 # machine-readable
python3 scripts/install.py --uninstall --harness all
python3 scripts/install.py --version                       # toolkit release label
```

`--yes` uses the detected harnesses (or opencode), `--mode link|copy`
(without it, what is installed keeps its mode and new items are linked, or
copied on Windows and when everything installed is a copy),
`--skills all|a,b`, `--agents all|a,b`, `--no-commands`, `--scope user|project`
and `--prune` (remove managed items you did not select). Nothing else is ever
removed, and items the toolkit did not install are only replaced with
`--force`, which always keeps a backup.

It only creates or removes files and links that belong to this repository, so
it never touches other files in your config directories. Command wrappers are
linked for opencode only.

## Per-agent notes

### opencode

Restart opencode after installing. Ask the agent to list its available skills,
or type `/` to see the commands.

### Claude Code

Restart Claude Code after installing. Skills are listed in `/help` and subagents
in `/agents`.

## Updating and uninstalling

- Symlink installs: just run `git pull`. The TUI's `U` key pulls for you when
  the clone has no local changes (or use `--offline` to disable the check).
- Any install, in one command: `python3 scripts/install.py --update --pull`
  fast-forwards the clone (only when it is clean and has not diverged;
  otherwise it says why and updates from the clone as it is) and then
  updates, in each harness, exactly what is already installed there, each
  item in its current mode. It never adds skills or harnesses you did not
  have, and it removes what is no longer in the toolkit (copies go to the
  backup folder first).
  After an install or update the CLI also says when a newer release exists.
  A clone on the `dev` branch is a development build (`2026.10.03.3-dev`,
  shown with a `[dev]` badge in the TUI): the installer tells you so, names
  the latest stable release, and offers newer dev builds. To go back to
  stable, run `git switch main && git pull`.
- Copy installs: the installer remembers the content hash and version of each
  copy in `<base>/.pamaga-toolkit.json` (per harness), so run the installer
  again (or `--status`) and it says *up to date*, *update available* or
  *modified locally*. `--yes` updates what changed but never overwrites your
  edits; add `--force` to overwrite a modified copy, which moves the old one
  to `<base>/.pamaga-backups/<YYYYmmdd-HHMMSS>/` first.
- Copies made by hand (option 2) that are identical to the clone are
  adopted the next time you run the installer in copy mode, so they get
  update tracking too; copies you changed are reported as *not installed by
  the toolkit* and left alone unless you pass `--force`.
- Uninstall: run `./scripts/install.sh --uninstall <target>` or
  `python3 scripts/install.py --uninstall --harness <ids>`; it removes only
  the symlinks and copies the manifest says are ours.
