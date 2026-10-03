# How to install PAMAGA Agent Toolkit

This toolkit is a folder of plain text files (Markdown). **Installing it just
means putting those files where your coding agent looks for them.** An
installer does that for you, with a menu: you do not need to edit anything by
hand.

You need three things:

1. **A coding agent**: [Claude Code](https://claude.com/claude-code),
   [opencode](https://opencode.ai) or [Antigravity CLI](https://antigravity.google)
   (`agy`). The toolkit adds skills to them.
2. **Python 3.9 or newer**, which runs the installer. Check with
   `python3 --version` (on Windows: `python --version`). If it is missing,
   get it from [python.org/downloads](https://www.python.org/downloads/)
   (on Windows, tick **"Add python.exe to PATH"** in the installer).
3. **The toolkit itself**, which you get in step 1 below.

> **Never used a terminal?** It is the window where you type commands.
> Open it like this:
> **Windows**: press the Windows key, type `PowerShell`, press Enter.
> **macOS**: press `Cmd + Space`, type `Terminal`, press Enter.
> **Linux**: press `Ctrl + Alt + T`.
> Every command below is typed there, followed by Enter.

---

## Step 1: get the toolkit

Pick **one** of these.

### Option A: with git (recommended)

Git lets you update later with one command. Check whether you have it:

```bash
git --version
```

If it prints a version, run:

```bash
git clone https://github.com/Pablomg02/pamaga-agent-toolkit.git
cd pamaga-agent-toolkit
```

If you use the GitHub CLI (`gh`), this is equivalent:

```bash
gh repo clone Pablomg02/pamaga-agent-toolkit
cd pamaga-agent-toolkit
```

If it says *command not found*, install git from
[git-scm.com/downloads](https://git-scm.com/downloads), reopen the terminal and
try again, or use Option B.

### Option B: download the ZIP (no git needed)

1. Open <https://github.com/Pablomg02/pamaga-agent-toolkit>.
2. Click the green **Code** button, then **Download ZIP**.
3. Unzip it (right click, *Extract all* on Windows; double click on macOS).
4. Move the folder somewhere permanent, such as your Documents folder. **Do not
   delete it afterwards**: the installer links to it.
5. In the terminal, go into the folder. The easy way: type `cd ` (with a
   trailing space), drag the folder into the terminal window, press Enter.

The ZIP is a snapshot: to get a newer version later, download it again and run
the installer again. (With git, one command does it.)

---

## Step 2: run the installer

### Linux and macOS

```bash
./scripts/install.sh
```

If you get *permission denied*, run `python3 scripts/install.py` instead.

### Windows (PowerShell)

```powershell
python scripts\install.py
```

If `python` is not recognised, try `py scripts\install.py`.

On Windows the installer **copies** the files by default, because links need
special permissions there. Everything works the same.

---

## Step 3: use the menu

A full-screen menu opens. You can accept the defaults at any point.

| Key | What it does |
| --- | --- |
| Up / down arrows | Move |
| Space | Mark or unmark the line under the cursor |
| Right arrow (or `Enter`) | Next step |
| Left arrow (or `Esc`) | Previous step |
| `Enter` on the review | Install (the right arrow never does) |
| `i` | Details about a skill |
| `?` | List all keys |

The bottom of each screen says what to do there and which keys work.

In order, it asks you to:

1. **Choose your agent(s)**: Claude Code, opencode, Antigravity CLI, or any
   combination. The ones already on your computer are detected.
2. **Choose what to install**: all the skills is a good start. At the bottom
   of the same list, under *options*, is the **mode**: *link* (a shortcut to
   this folder: `git pull` updates everything instantly) or *copy*
   (independent files). If unsure, keep the suggestion.
3. **Review and apply.** Nothing happens until you confirm.

Then **restart your agent**. That is the step people forget.

## Step 4: check that it worked

- **Claude Code**: type `/` and look for commands such as `/make-plan`, or ask
  "what skills do you have?".
- **opencode**: the same; type `/` to see the commands.
- **Antigravity CLI**: run `/skills` inside `agy`; each skill is also a
  `/make-plan` style command on its own.

Then try it: *"Plan a CSV export for my project"* or `/make-plan`.

---

## Updating

From inside the toolkit folder:

```bash
python3 scripts/install.py --update --pull   # Windows: python scripts\install.py --update --pull
```

This downloads the latest version (needs git) and updates only what you had
installed. Installed with the ZIP? Download the new ZIP and run the installer
again.

To see what is installed and where:

```bash
python3 scripts/install.py --status
```

## Uninstalling

```bash
./scripts/install.sh --uninstall all        # Windows: python scripts\install.py --uninstall --harness all
```

It removes only what the toolkit installed and never touches your other files.

## Something went wrong?

| Problem | Fix |
| --- | --- |
| `python3: command not found` | Install Python 3.9+ (see the top of this page). |
| `git: command not found` | Install git, or use the ZIP (Option B). |
| `permission denied` on `install.sh` | Run `python3 scripts/install.py` instead. |
| Windows: link or permission error | Choose **copy** mode in the menu. |
| The skills do not appear | Restart the agent completely. |

## For advanced users

- Non-interactive install: `python3 scripts/install.py --yes --harness all --offline`
- Install into a single project instead of your user folder: `--scope project`
- Exact locations, manual copy or symlink commands, and every flag:
  [docs/INSTALL.md](docs/INSTALL.md)
