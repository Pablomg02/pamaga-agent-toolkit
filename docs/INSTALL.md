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
| Antigravity CLI | `~/.gemini/config/skills/<name>/SKILL.md` | not installed (see below) | not needed |
| Grok CLI | `~/.grok/skills/<name>/SKILL.md` | `~/.grok/agents/<name>.md` | not needed |

Notes:

- opencode also reads skills from `~/.claude/skills/`, so skills installed for
  Claude Code are picked up there too. When the installer targets both, it
  puts the skills only in `~/.claude/skills/` (opencode would otherwise list
  each one twice) and gives opencode just its agents and command wrappers.
  The same goes when only opencode is selected but `~/.claude/skills/`
  already has a skill: it is not copied again. The TUI and `--status` show
  such skills as installed in opencode "via Claude Code", and removing them
  from Claude Code alone warns that opencode will lose them too.
  If you install by hand, do the same: skills in one place only.
- In project scope, opencode also reads `.agents/skills/`, the directory
  Antigravity CLI uses: targeting both in a project installs the skills only
  there, again to avoid duplicates.
- Grok CLI reads the same shared dirs: `~/.claude/skills/` at user scope, and
  `.claude/skills/` and `.agents/skills/` in a project. The installer shares
  them as it does for opencode, so a skill is not copied into `~/.grok/skills/`
  (or `.grok/skills/`) when Grok already sees it. `--status` and the TUI show
  that as "via Claude Code" or "via Antigravity CLI". Grok gets its own copies
  when no shared dir gives it the skill, or when its Claude compatibility for
  skills is off: `GROK_CLAUDE_SKILLS_ENABLED=false`, or `skills = false` under
  `[compat.claude]` in `~/.grok/config.toml`. The same key may also be written
  `claude.skills = false` under `[compat]`, or `compat.claude.skills = false`
  before any table; spaces around the dots are ignored. A quoted key or an
  inline table (`claude = { skills = false }`) is not understood and leaves
  the switch on: use the environment variable then. Do not install `commands/`
  for Grok. Each wrapper would become a skill with the same name as the real
  one. In a project, Grok loads those skills only after the folder is trusted
  (`grok --trust`, or `/hooks-trust` inside Grok). If `GROK_HOME` is set, the
  installer uses it in place of `~/.grok`, both for the user install and for
  `config.toml`.
- Before it changes anything, the installer prints one line per selected
  harness and provider when the harness could read that provider's skills.
  Shared: `Grok CLI: 3 skill(s) not copied to ~/.grok/skills; it already reads them from ~/.claude/skills (Claude Code).`
  Not shared, because a setting stopped it: `Grok CLI: 3 skill(s) copied to ~/.grok/skills; it does not read ~/.claude/skills (GROK_CLAUDE_SKILLS_ENABLED=false).`
  opencode uses the same two sentences.
- Claude Code, Antigravity CLI and Grok CLI register every skill as `/<name>`
  on their own. Do not install `commands/` there: the wrappers would collide
  with the skills.
- Antigravity CLI also reads global skills from
  `~/.gemini/antigravity-cli/skills/` and `~/.gemini/skills/` (the *Shared*
  location, used together with Gemini CLI). The installer uses
  `~/.gemini/config/`, the root shared by all the Antigravity surfaces, and
  leaves the other two alone.
- Antigravity CLI wants each agent as `agents/<name>/agent.md`, not
  `agents/<name>.md`, so the installer gives it skills only. In the manual
  steps below, skip the `agents` line for it.
- All of them also support project-scoped installs: `.opencode/`, `.claude/`,
  `.agents/` and `.grok/` inside a repository. This guide covers the global
  (user) scope.

## Option 1: symlinks (recommended)

Symlinks keep this repository as the single source of truth: after `git pull`,
your agents use the new content immediately.

```bash
REPO="$HOME/GitHub/pamaga-agent-toolkit"
DEST="$HOME/.config/opencode"   # $HOME/.claude for Claude Code; $HOME/.gemini/config for Antigravity CLI; $HOME/.grok for Grok CLI

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
DEST="$HOME/.config/opencode"   # $HOME/.claude for Claude Code; $HOME/.gemini/config for Antigravity CLI; $HOME/.grok for Grok CLI

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

### Antigravity CLI

Restart Antigravity CLI (`agy`) after installing. Skills are model-invoked and
also registered as `/<name>` commands on their own; run `/skills` inside `agy`
to see the list.

### Grok CLI

Grok CLI reloads skills when the files change; restart it if a change does not
show up. Type `/` to list them. `grok inspect` shows where each one comes from.

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
  A clone on the `dev` branch is a development build (its version is the
  commit, shown with a `[dev]` badge in the TUI): the installer tells you so,
  names the latest stable release, and says when `origin/dev` has newer
  commits. To go back to stable, run `git switch main && git pull`.
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
