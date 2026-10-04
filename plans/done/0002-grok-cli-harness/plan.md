---
id: "0002"
title: "Add Grok CLI as an installer harness"
type: plan
created: 2026-10-04
---

# 0002 — Add Grok CLI as an installer harness

## Justification

The user also works with Grok CLI (`grok`, xAI) and wants to install the
toolkit there with the same installer (TUI, `--yes`, `--update`,
`--uninstall`, `install.sh`). Today the installer knows only opencode, Claude
Code and Antigravity CLI.

Grok already lists the toolkit's skills, but only by accident: it reads
`~/.claude/skills/` for Claude Code compatibility (see
[research/grok-discovery.md](research/grok-discovery.md)). The installer does not know
that, so:

- installing for Claude Code and then removing it gives no warning that Grok
  loses its skills;
- a user with Grok but no Claude Code cannot install anything for Grok;
- installing skills into `~/.grok/skills/` as well would leave two copies,
  and the `~/.grok` one would silently shadow the Claude one.

This is the same situation as opencode, which also reads Claude's folder, and
the installer already models it with `skills_from`.

### Goals

- `grok` is a fourth harness in `scripts/installer/harnesses.py`, available
  in the TUI, the CLI (`--harness grok`, `--harness all`) and `install.sh`
  (`grok` and `all` targets), at user scope (`~/.grok`) and project scope
  (`.grok`).
- Grok shares skills like opencode: it reads Claude's skills dir at both
  scopes and the Antigravity `.agents` dir in a project, so a skill is never
  installed twice for it, and `--status` and the TUI show those skills as
  "via Claude Code" or "via Antigravity CLI".
- When Grok's Claude compatibility for skills is turned off
  (`GROK_CLAUDE_SKILLS_ENABLED=false` or `[compat.claude] skills = false` in
  `~/.grok/config.toml`), Grok does not count Claude as a provider and gets
  its own copies.
- Grok gets skills and agents, never the opencode command wrappers.
- The installer says plainly, for every selected harness that could read
  another harness's skills dir (opencode and Grok), which of the two things
  it is doing: *not copying* the skills because the harness already reads
  them from the other dir, or *copying* them into the harness's own dir
  because a setting stops it reading the other one. One line per harness and
  provider, shown before anything is applied, in the CLI and in the TUI
  review screen, built by one shared function.
- Tests and docs cover Grok like the other harnesses.

### Non-goals

- Reading other Grok sources: `~/.agents/skills`, `~/.cursor/skills`,
  `[skills] paths` in Grok's config, plugins and marketplaces. The toolkit
  never installs there, so they are not providers.
- Packaging the toolkit as a Grok (or Claude Code) plugin or marketplace.
- Changing how opencode, Claude Code or Antigravity are installed.
- Handling Grok's folder trust: the installer writes `.grok/` in a project,
  but Grok loads project skills only after the user trusts the folder. That
  is documented, not automated.
- More sharing messages than the one line per harness and provider: no
  per-skill lines, no new columns in `--status`, no notes on `--update` or
  `--uninstall` (the existing loss warning already covers removals), and no
  extra text on the TUI harnesses or components screens, where the existing
  "via ..." labels stay as they are.
- Fixing ticket 0001 (containment of removals). Grok's project folder
  `.grok/` falls under the same issue and is fixed together with the others
  when 0001 is done.

## Plan

### Context

Installer layout (see `docs/CONVENTIONS.md`, "Bundled scripts"):

- `scripts/installer/harnesses.py`: `HarnessSpec` registry (`HARNESS_SPECS`)
  and `all_harnesses(scope, project, env)`, which builds `Harness` objects.
  `skills_from` (user scope) and `project_skills_from` list the harness ids
  whose skills dir this harness also reads. opencode has
  `skills_from=("claude",)` and `project_skills_from=("claude", "antigravity")`.
  `_home(env)` resolves HOME (USERPROFILE fallback).
- `scripts/installer/actions.py`: `shared_source()` (around line 118) returns
  the first provider in `harness.skills_from` that is selected or has the
  skill on disk; `_plan_harness()` (around line 238) skips installing a skill
  that has a provider; `shared_skill_losses()` (around line 150) warns when
  removing a skill from a provider takes it away from a reader; commands and
  agents are filtered with `supports_commands` / `supports_agents` (around
  lines 395 and 440).
- `scripts/installer/cli.py`: `--harness` help text (line 45),
  `resolve_harnesses()` (detected harnesses for `--yes`, falling back to
  opencode), `shared_notes()` and the "via" cells of `--status` (around line
  480). All of them are generic over `skills_from`.
- `scripts/installer/tui/app.py`: generic over `self.harnesses`; "via"
  labels come from `shared_source`.
- What the installer says today about shared skills (verified):
  - A skill that a harness reads from another dir gets no action line for
    that harness in the plan, so the plan alone does not explain why it is
    missing.
  - CLI: `shared_notes()` (`cli.py` around line 307) builds
    `Note: <label> reads N skill(s) from <dir> (<provider>), so they are not copied to its own dir.`,
    but `main` prints it only **after** `apply_actions` (around line 202),
    followed by `Older copies in its own skills dir are kept; run with --prune to remove them.`
    when some `keep` action has a reason starting with `already read from`.
    `tests/test_installer_cli.py:103` asserts `reads 3 skill(s) from`.
  - TUI review screen (`_render_review`, `app.py` around lines 1208-1218)
    rebuilds the same count inline and shows
    `<label> reads N skill(s) from <dir>, so they are not copied again (no duplicates).`
  - Nothing is said when a harness gets its own copies because it does not
    read the other dir.
- `scripts/install.sh`: legacy targets `opencode|claude|antigravity|all`,
  hard-coded.
- Docs naming the harnesses: `README.md` (lines 7-8, 23), `INSTALL.md`
  (lines 11, 114, 128-130), `docs/INSTALL.md` (table "Where each agent
  looks", notes, per-agent notes, option 1 and 2 `DEST` comments),
  `docs/CONVENTIONS.md` (intro line, "Invoking a skill", "Agents").
- Tests: `tests/test_installer_state.py` (harness list, bases, labels,
  `skills_from`; several tests unpack exactly three harnesses),
  `tests/test_installer_actions.py` (sharing and losses),
  `tests/test_installer_cli.py`, `tests/test_install.py` (shim, with a fake
  HOME; `test_..._uninstall` loops over the three folders around line 76),
  `tests/test_installer_tui.py` (`World` builds its own `Harness` objects
  around lines 26-43; `test_every_screen_fits_the_terminal`).

Facts about Grok are in [research/grok-discovery.md](research/grok-discovery.md).

Checks (from `docs/CONVENTIONS.md`), run from the repository root:

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests
shellcheck scripts/install.sh
```

### Approach

Add one `HarnessSpec` for Grok, modelled on opencode: base `~/.grok`
(project `.grok`), binary `grok`, no command wrappers, agents supported,
`skills_from=("claude",)` and `project_skills_from=("claude", "antigravity")`.
Because the planning, status and TUI code is already generic over
`skills_from`, sharing, "via" labels and loss warnings work without changes
there.

The only new logic is the compatibility switch. `HarnessSpec` gets an
optional `skills_from_switches` field: pairs of `(provider id,
CompatSwitch)`. `all_harnesses()` drops a provider from the built harness's
`skills_from` when its switch is off. Grok's switch for `claude` reads the
environment variable `GROK_CLAUDE_SKILLS_ENABLED` and the key
`compat.claude.skills` in `<home>/.grok/config.toml`. The same user-level
switch applies at both scopes, since Grok reads it only from the user config.
Python 3.9 has no `tomllib`, so a small line-based reader extracts that one
boolean. A provider dropped by a switch is not forgotten: the harness keeps
it in `skills_from_disabled` together with a short reason, so the installer
can say why it copies.

Transparency without clutter: one pure function, `sharing_notes()` in
`actions.py`, turns the harnesses, scans, selection and wanted skills into a
list of `SharingNote` records (harness, provider, count, shared or not,
reason). The CLI and the TUI only format those records with the same
wording, so there is one source of truth and no logic in the UI. The CLI
prints them right after the plan and before applying; the TUI keeps them in
the review header where today's line is. A harness gets a line only when the
question is real: the provider is selected in this run or already holds one
of the wanted skills. A Grok user without Claude Code sees nothing about
Claude.

Discarded:

- Always giving Grok its own copy in `~/.grok/skills`: two copies to keep in
  sync, and the Grok one silently shadows Claude's (user decision D1).
- Putting the switch check inside `shared_source()`: it would need the
  environment at every call site. Resolving it once in `all_harnesses()`,
  which already receives `env`, keeps `actions.py` untouched.
- A full TOML parser: too much code for one boolean, and no third-party
  packages are allowed.

### Decisions

| # | Decision | Rationale | Source |
| --- | --- | --- | --- |
| D1 | Grok shares skills like opencode: `skills_from=("claude",)`, `project_skills_from=("claude", "antigravity")`. | One copy per skill; same model as opencode; Grok reads exactly those dirs ([research](research/grok-discovery.md)). | user |
| D2 | Honour Grok's switch for Claude skills: when off, `claude` is not a provider for Grok. | Otherwise Grok would end up with no skills while the installer believes it has them. | user |
| D3 | Precedence: if `GROK_CLAUDE_SKILLS_ENABLED` is set (non-empty) in `env`, it decides alone (off when its stripped, lower-cased value is `false`, `0`, `no` or `off`; on otherwise). If not set, `compat.claude.skills = false` in `<home>/.grok/config.toml` turns it off. A missing or unreadable file, or a missing key, means on. | Environment variables usually override config files; on is Grok's default. | research |
| D4 | The config reader understands three spellings of the key: `skills = <bool>` under `[compat.claude]`, `claude.skills = <bool>` under `[compat]`, and `compat.claude.skills = <bool>` before any table. Spaces around dots inside the header or key are ignored. Comments (`#` and everything after it) are stripped. Quoted keys and inline tables (`claude = { skills = false }`) are not understood and count as on; docs/INSTALL.md says so. The first match wins. | Covers how people write TOML by hand without a parser; the documented form is the first one. | research |
| D5 | `supports_commands=False` for Grok. | Grok turns every `commands/*.md` into a skill with the same name as the real skill. | research |
| D6 | `supports_agents=True` for Grok: agents go to `~/.grok/agents/<name>.md` even when Claude Code also has them. | Same `.md` format; Grok deduplicates agents by name, so a second copy in `~/.claude/agents` is harmless. No `agents_from` mechanism is needed. | research |
| D7 | Harness id `grok`, label `Grok CLI`, binary `grok`, `user_root="home"`, `user_dir=".grok"`, `project_dir=".grok"`, restart hint `Grok CLI reloads skills on its own; restart it if a change does not show up.` | Matches Grok's own names and folders; Grok reloads skills when files change. | research |
| D8 | Append Grok at the end of `HARNESS_SPECS`. | Order in the TUI and in `all`; existing ids keep their position, so `--yes` still falls back to opencode first. | author |
| D9 | `install.sh` gets a `grok` target and `all` becomes `opencode,claude,antigravity,grok`. | Keep the legacy shim complete. | author |
| D10 | Release type: MINOR (no `[patch]` marker). | New installer behaviour (AGENTS.md, "Versions"). | author |
| D11 | Sharing is explained by one function, `sharing_notes()` in `actions.py`, returning `SharingNote` records. `cli.shared_notes()` and the TUI review header format them and contain no counting logic. | One source of truth; today's CLI and TUI duplicate the count with different wording. | user |
| D12 | Exact wording, identical in CLI and TUI. Shared: `<Harness label>: N skill(s) not copied to <own skills dir>; it already reads them from <provider skills dir> (<Provider label>).` Not shared: `<Harness label>: N skill(s) copied to <own skills dir>; it does not read <provider skills dir> (<reason>).` The CLI prefixes nothing (no `Note:`). | States the action and the reason in one line, with the real paths. | user |
| D13 | A note appears only for a selected harness and a provider in its `skills_from` (shared) or `skills_from_disabled` (not shared), and only when N > 0, where N counts the wanted skills (after `required_closure`) for which the provider is selected in this run or has the skill on disk (`_on_disk`). | No noise for users who do not use the provider; the line appears exactly when the reader would otherwise wonder. | user |
| D14 | Where notes show: CLI, after `_print_plan` and before `apply_actions`, for install runs only (`selection is not None`), followed by the existing `--prune` hint when it applies; TUI, review screen header (replacing today's line), with the shared notes in the muted colour and the not-shared ones in `THEME["check"]` so they stand out. Nowhere else. | Seen before anything changes; no extra screens or columns. | user |
| D15 | Reason strings in `skills_from_disabled`: `GROK_CLAUDE_SKILLS_ENABLED=<value as set>` when the env var decided, `compat.claude.skills = false in <absolute config path>` when the file did. Built generically from `CompatSwitch`: `f"{switch.env}={value}"` and `f"{switch.table}.{switch.key} = false in {path}"`. | Tells the user exactly what to change to share again. | author |

### Tasks

#### T1 — Grok harness spec and compatibility switch

- **Objective:** `all_harnesses()` returns a fourth harness `grok` at both
  scopes, with `skills_from` resolved according to D1-D3, without changing the
  other three.
- **Files:** `scripts/installer/harnesses.py`, `tests/test_installer_state.py`
- **Depends on:** —
- **Details:**
  - Add a frozen dataclass:
    ```python
    @dataclass(frozen=True)
    class CompatSwitch:
        """A harness setting that can stop it reading another harness's skills dir."""
        env: str      # environment variable; set and false-like turns it off
        config: str   # config file, relative to the home directory
        table: str    # TOML table holding the key, e.g. "compat.claude"
        key: str      # boolean key in that table, e.g. "skills"
    ```
  - Add to `HarnessSpec`:
    `skills_from_switches: tuple[tuple[str, CompatSwitch], ...] = ()`.
  - Add `_switch_off_reason(switch: CompatSwitch, env: Mapping[str, str], home: Path) -> str | None`
    implementing D3: `None` when the switch is on, otherwise the D15 reason
    string. Add `_toml_bool(text: str, table: str, key: str) -> bool | None`
    implementing D4 (`None` when the key is not found).
  - Add to `Harness`:
    `skills_from_disabled: tuple[tuple[str, str], ...] = ()` — pairs of
    `(provider id, reason)` for providers this harness would read but a
    setting turned off. Comment it like `skills_from`.
  - In `all_harnesses()`, compute `home = _home(env)` for both scopes and
    pass the provider tuple through a helper
    `_reachable(spec, providers, env, home) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]`
    that splits it into the providers kept (order preserved) and the
    disabled ones with their reasons. `_build` receives both and sets
    `skills_from` and `skills_from_disabled`.
  - Append the Grok spec (D7, D1, D5, D6, D8) with
    `skills_from_switches=(("claude", CompatSwitch(env="GROK_CLAUDE_SKILLS_ENABLED", config=".grok/config.toml", table="compat.claude", key="skills")),)`
    and a comment saying why (Grok reads Claude's skills dir unless this
    switch is off; see docs/INSTALL.md).
  - Update the module docstring only if it names the harnesses (it does not
    today).
  - Update existing tests that unpack or list three harnesses to the four ids
    `["opencode", "claude", "antigravity", "grok"]`.
- **Acceptance criteria:**
  - [x] `python3 -m unittest tests.test_installer_state` passes.
  - [x] New tests in `tests/test_installer_state.py` check: user base
        `<home>/.grok` and project base `<project>/.grok`; label `Grok CLI`,
        binary `grok`, `supports_commands` false, `supports_agents` true;
        `skills_from == ("claude",)` at user scope and
        `("claude", "antigravity")` at project scope with an empty `env`
        apart from HOME.
  - [x] New tests check the switch: `GROK_CLAUDE_SKILLS_ENABLED` set to
        `false`, `FALSE`, `0`, `no`, `off` gives `skills_from == ()` (user)
        and `("antigravity",)` (project); set to `true` wins over a config
        file that says `false`; unset with each of the three D4 spellings
        set to `false` turns it off; the same spellings with `true`, a
        commented-out line (`# skills = false`), the key under another table
        (`[compat.cursor]`), a missing file and an inline table all leave it
        on.
  - [x] When the switch is off, Grok's `skills_from_disabled` is
        `(("claude", "GROK_CLAUDE_SKILLS_ENABLED=false"),)` for the env case
        and `(("claude", "compat.claude.skills = false in <home>/.grok/config.toml"),)`
        for the file case; when it is on, `skills_from_disabled == ()`.
  - [x] opencode's `skills_from` is unaffected by the Grok switch (a test
        with the switch off still gets `("claude",)` for opencode, and
        `skills_from_disabled == ()`).

#### T2 — Sharing, losses and planning with Grok

- **Objective:** prove with tests that the generic planner treats Grok like
  opencode: no duplicate skills, no wrappers, agents installed, loss
  warnings, and its own copies when the switch is off.
- **Files:** `tests/test_installer_actions.py` (production code changes only
  if a test shows a real gap; then in `scripts/installer/actions.py`, and the
  change is recorded under *Implementation* as a deviation).
- **Depends on:** T1
- **Acceptance criteria:**
  - [x] `python3 -m unittest tests.test_installer_actions` passes.
  - [x] Test: selecting `claude` and `grok` with a skill installs it in
        `claude` only, and plans no `skill` install for `grok`.
  - [x] Test: selecting `grok` alone while the skill is on disk in Claude's
        dir plans no `skill` install for `grok`; with an empty Claude dir it
        installs it in `~/.grok/skills`.
  - [x] Test: `grok` never gets a `command` action even with
        `Selection(commands=True)`, and gets an `agent` install when an
        agent is selected.
  - [x] Test: with harnesses built from an `env` whose
        `GROK_CLAUDE_SKILLS_ENABLED=false`, selecting `claude` and `grok`
        installs the skill in both.
  - [x] Test: in project scope, selecting `antigravity` and `grok` installs
        the skill only in `antigravity`.
  - [x] Test: uninstalling a skill from `claude` while `grok` has some
        toolkit item installed (for example an agent) returns a loss
        `("grok", "<skill>", "claude")` from `shared_skill_losses`.

#### T3 — One sharing note, used by the CLI and the TUI

- **Objective:** before anything is applied, the user reads for each
  selected harness whether its skills are *not copied* (already read from
  another harness's dir) or *copied* (a setting stops it reading that dir),
  with the wording of D12, from a single function.
- **Files:** `scripts/installer/actions.py`, `scripts/installer/cli.py`,
  `scripts/installer/tui/app.py`, `tests/test_installer_actions.py`,
  `tests/test_installer_cli.py`, `tests/test_installer_tui.py`
- **Depends on:** T1, T2
- **Details:**
  - In `actions.py`, next to `shared_source`:
    ```python
    @dataclass(frozen=True)
    class SharingNote:
        """Why a harness's skills are, or are not, copied into its own dir."""
        harness_id: str
        provider_id: str
        count: int
        shared: bool      # True: read from the provider's dir, not copied
        reason: str = ""  # when not shared: the setting that turned it off

    def sharing_notes(
        harnesses: Iterable[Harness],      # every harness of the scope
        scans: Mapping[str, Mapping[str, Installed]],
        selection: Selection,
        wanted: set[str],                  # catalog.required_closure(selection.skills)
    ) -> list[SharingNote]:
    ```
    For each harness whose id is in `selection.harness_ids`, in harness
    order: one shared note per provider in `skills_from`, counting the
    wanted skills for which `shared_source(harness, name, scans,
    selection.harness_ids)` returns that provider; then one not-shared note
    per `(provider, reason)` in `skills_from_disabled`, counting the wanted
    skills for which the provider is in `selection.harness_ids` or
    `_on_disk(scans, provider, name)` is true. Notes with `count == 0` are
    dropped (D13). Export both names from the module like the others.
  - Add one formatter in `actions.py`, used by both front ends:
    `describe_sharing(note: SharingNote, harnesses: Iterable[Harness]) -> str`,
    returning the D12 sentence (labels and `dir_for("skill")` from the
    harness list).
  - `cli.py`: `shared_notes()` keeps its name and signature but becomes
    `[describe_sharing(n, everyone) for n in sharing_notes(everyone, scans, selection, wanted)]`.
    Move the block that prints the notes and the `--prune` hint from after
    `apply_actions` to just after `_print_plan` and the loss warnings, still
    only when `selection is not None` and not uninstalling (D14).
  - `app.py` `_render_review`: replace the inline counting loop with
    `sharing_notes(self.harnesses, self.scans, <current Selection>, self._wanted())`
    and `describe_sharing`, muted colour for shared notes and
    `THEME["check"]` for not-shared ones. Get the selection from the
    existing `self._selection()` (`app.py` around line 271); do not build a
    second one by hand.
  - Update `tests/test_installer_cli.py:103` to the new wording.
- **Acceptance criteria:**
  - [x] `python3 -m unittest tests.test_installer_actions tests.test_installer_cli tests.test_installer_tui` passes.
  - [x] Unit tests on `sharing_notes`: claude+grok selected gives
        `SharingNote("grok", "claude", N, True)`; grok alone with nothing in
        Claude's dir gives `[]`; grok alone with the skills on disk in
        Claude's dir gives the shared note; claude+grok with the switch off
        gives `SharingNote("grok", "claude", N, False, "GROK_CLAUDE_SKILLS_ENABLED=false")`;
        grok alone with the switch off and an empty Claude dir gives `[]`.
  - [x] Unit test on `describe_sharing` for both kinds, comparing the whole
        string with the D12 template filled with fake-HOME paths.
  - [x] CLI test: `--yes --harness claude,grok --skills make-plan --offline`
        prints `Grok CLI: 2 skill(s) not copied to` and the line appears in
        stdout **before** the `Done.` line and before any line of
        `apply_actions` output that follows the plan (assert on the index in
        stdout relative to the plan's last `link` line and `Done.`).
  - [x] CLI test: the same run with `GROK_CLAUDE_SKILLS_ENABLED=false` in
        the environment links the skills into both `<home>/.claude/skills`
        and `<home>/.grok/skills` and prints
        `Grok CLI: 2 skill(s) copied to <home>/.grok/skills; it does not read <home>/.claude/skills (GROK_CLAUDE_SKILLS_ENABLED=false).`
  - [x] CLI test: `--yes --harness grok --skills make-plan --offline` with
        an empty HOME prints no line containing `skill(s) not copied` or
        `skill(s) copied`.
  - [x] TUI test: with claude and grok selected, the review render contains
        `Grok CLI: ` and `not copied to`; `grep -n "reads .* skill(s) from" scripts/installer/tui/app.py scripts/installer/cli.py`
        finds nothing (the old inline wording is gone).

#### T4 — CLI and install.sh

- **Objective:** Grok is reachable from every entry point.
- **Files:** `scripts/installer/cli.py`, `scripts/install.sh`,
  `tests/test_installer_cli.py`, `tests/test_install.py`
- **Depends on:** T1
- **Details:**
  - `cli.py` line 45: help text
    `--harness opencode,claude,antigravity,grok|all`.
  - `install.sh`: `GROK_DIR="$HOME/.grok"`; usage line
    `  grok         Skills and agents for Grok CLI (skills are already /commands)`;
    location line `  Grok CLI       ${GROK_DIR}/{skills,agents}`; extend the
    parenthesised note to say that opencode and Grok CLI both read
    `${CLAUDE_DIR}/skills`; accept `grok` in the argument `case`; map
    `grok) HARNESSES="grok" ;;` and `all` to
    `opencode,claude,antigravity,grok`.
- **Acceptance criteria:**
  - [x] `shellcheck scripts/install.sh` reports nothing.
  - [x] `python3 -m unittest tests.test_installer_cli tests.test_install` passes.
  - [x] New CLI test: `--yes --harness grok --skills make-plan --offline`
        with a fake HOME links `make-plan` and `plans-convention` into
        `<home>/.grok/skills` and creates no `<home>/.grok/commands`.
  - [x] New CLI test: `--yes --harness claude,grok --skills make-plan --offline`
        links the skills only into `<home>/.claude/skills`;
        `<home>/.grok/skills` has no symlinks (the sharing line itself is
        tested in T3).
  - [x] New CLI test: after that install, `--status` shows `via Claude Code`
        in the Grok column for `make-plan`.
  - [x] New shim test: `install.sh grok` links every skill into
        `<home>/.grok/skills` and none into `<home>/.grok/commands`; the
        `--uninstall all` test also checks `<home>/.grok`.

#### T5 — TUI with four harnesses

- **Objective:** the TUI shows Grok and stays inside the terminal at every
  tested size.
- **Files:** `tests/test_installer_tui.py` (and `scripts/installer/tui/*.py`
  only if the new test fails; record any change as a deviation).
- **Depends on:** T1
- **Acceptance criteria:**
  - [x] `World` in `tests/test_installer_tui.py` gets a third and fourth
        harness option: a test variant builds the world with four harnesses
        (opencode, claude, antigravity, grok, the last with
        `skills_from=("claude",)`), and `test_every_screen_fits_the_terminal`
        (or a copy of it for this variant) passes for all screens, widths and
        heights.
  - [x] Test: with a skill on disk in Claude's dir and Grok selected, the
        components screen render contains `via Claude Code` for Grok.
  - [x] `python3 -m unittest tests.test_installer_tui` passes.

#### T6 — Documentation

- **Objective:** every place that lists the supported harnesses includes Grok
  CLI and explains what it reads.
- **Files:** `docs/INSTALL.md`, `INSTALL.md`, `README.md`,
  `docs/CONVENTIONS.md`
- **Depends on:** T1, T3, T4
- **Details:**
  - `docs/INSTALL.md`: row `| Grok CLI | ~/.grok/skills/<name>/SKILL.md | ~/.grok/agents/<name>.md | not needed |`;
    a note that Grok also reads `~/.claude/skills/` (and `.claude/skills/`
    and `.agents/skills/` in a project), so the installer shares them as for
    opencode, unless Grok's Claude compatibility is off
    (`GROK_CLAUDE_SKILLS_ENABLED=false` or `[compat.claude] skills = false`;
    the D4 limits on how the key may be written); that Grok must not get
    `commands/` because each wrapper becomes a skill with the same name;
    that Grok loads project skills only in a trusted folder (`--trust` or
    `/hooks-trust`); that the installer says, before applying, for each
    harness whether it did not copy the skills (and where it reads them
    from) or copied them (and which setting stops sharing), with one example
    of each D12 line; `DEST` comments in options 1 and 2 mention
    `$HOME/.grok`; a "### Grok CLI" per-agent note (skills reload on their
    own, `/` lists them, `grok inspect` shows where each comes from).
  - `INSTALL.md`, `README.md`: add Grok CLI wherever opencode, Claude Code
    and Antigravity CLI are listed, plus how to see the skills in Grok
    (`/` or `grok inspect`) next to the existing per-agent lines in
    `INSTALL.md`.
  - `docs/CONVENTIONS.md`: intro names Grok CLI; "Invoking a skill" gets a
    Grok bullet (skills are `/<name>` already, no wrappers); "Agents" says
    Grok uses the same `agents/<name>.md` format.
- **Acceptance criteria:**
  - [x] `grep -n "Grok" docs/INSTALL.md INSTALL.md README.md docs/CONVENTIONS.md`
        shows a hit in every one of the four files.
  - [x] `grep -n "GROK_CLAUDE_SKILLS_ENABLED" docs/INSTALL.md` has a hit.
  - [x] `python3 scripts/validate.py` passes.

### Execution

Mode: single agent

The tasks are small and all hang on T1's spec; T2, T4 and T5 are mostly
tests over code that does not change; T3 touches `actions.py`, `cli.py` and `app.py`,
the same files T4 and T5 test. One agent working T1 → T2 → T3 → T4 → T5 → T6
is cheaper than coordinating packages.

### Verification

From the repository root:

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests
shellcheck scripts/install.sh
```

All three pass. Then a manual check on a machine with Grok installed, with a
scratch HOME so the real config is untouched:

```bash
H=$(mktemp -d)
HOME=$H python3 scripts/install.py --yes --harness claude,grok --offline
HOME=$H python3 scripts/install.py --status          # Grok column: "via Claude Code"
cp ~/.grok/auth.json ~/.grok/config.toml $H/.grok/ 2>/dev/null
(cd /tmp && HOME=$H grok inspect --json) | python3 -c "import json,sys; print(sorted(s['name'] for s in json.load(sys.stdin)['skills'] if s['source']['type']=='user'))"
```

The last command lists every toolkit skill once. Repeat the first command
with `GROK_CLAUDE_SKILLS_ENABLED=false` in a fresh `H`: the output says
`Grok CLI: N skill(s) copied to $H/.grok/skills; it does not read $H/.claude/skills (GROK_CLAUDE_SKILLS_ENABLED=false).`
before applying, and both skills dirs get the links.

### Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Grok changes the folders it reads or the name of the switch. | The installer shares into a folder Grok no longer reads. | Facts and version are recorded in research/grok-discovery.md; `grok inspect` in *Verification* shows it quickly. Accepted. |
| The line-based reader misses an unusual TOML spelling of the switch. | Grok has Claude compatibility off but the installer still shares; Grok sees no toolkit skills. | D4 covers the documented and common forms; docs/INSTALL.md explains the limit and the env var as the reliable way. |
| `--yes` with no `--harness` now also detects Grok (`~/.grok` or `grok` on PATH). | A user running `--yes` gets the Grok agents installed too. | Intended: same behaviour as the other harnesses. Tests use a fake HOME and explicit `--harness`. |
| Ticket 0001 (unsafe removals in project scope) also applies to `.grok/`. | Same as today for the other folders. | Out of scope; 0001 fixes all harness folders at once. |

### Open questions

## Implementation

Baseline (2026-10-04): `python3 -m unittest discover -s tests` — 308 tests, OK.

- [x] T1 — Grok harness spec and compatibility switch — `python3 -m unittest tests.test_installer_state` 40 passed
- [x] T2 — sharing, losses and planning with Grok — `python3 -m unittest tests.test_installer_actions` passed; no production change, the planner already follows `skills_from`
- [x] T3 — sharing notes in the CLI and the TUI — `python3 -m unittest tests.test_installer_actions tests.test_installer_cli tests.test_installer_tui` passed; `grep "reads .* skill(s) from"` on `cli.py` and `tui/app.py` finds nothing
- [x] T4 — CLI and install.sh — `python3 -m unittest tests.test_installer_cli tests.test_install` passed; `shellcheck scripts/install.sh` (v0.10.0) reports nothing
- [x] T5 — TUI with four harnesses — `python3 -m unittest tests.test_installer_tui` 36 passed; no TUI change beyond T3
- [x] T6 — documentation — Grok named in all four docs; `python3 scripts/validate.py` ok, 0 warnings

Deviations:
- T3/T4: the plan's examples say `make-plan` closes over 2 skills (`make-plan`, `plans-convention`). `required_closure` also includes `research-topic` (already locked by `test_yes_with_a_subset_links_only_the_closure`), so the notes and the Grok-only install use those 3 skills. Counting still follows D13. A full install is 11 skills, which is what the scratch-HOME run printed.
- Review fixes (2026-10-04): the Grok user base and its `config.toml` follow `GROK_HOME` when it is set (`HarnessSpec.user_env`, `_user_base`; `CompatSwitch.config` is now relative to that base), and `install.sh` shows `${GROK_HOME:-$HOME/.grok}`. The CLI and `install.sh` tests drop `GROK_HOME` and `GROK_CLAUDE_SKILLS_ENABLED` from the inherited environment, so a runner's own Grok setup cannot change results or write outside the fake HOME. `docs/INSTALL.md` now says Grok also gets its own copies when no shared dir has the skill. Two new tests: 331 pass with and without both variables set.

## Results

`grok` is a fourth harness, at `~/.grok` and `.grok`. It shares skills with Claude Code, and in a project with Antigravity CLI, unless `GROK_CLAUDE_SKILLS_ENABLED` or `compat.claude.skills` in `~/.grok/config.toml` turns that off. It receives skills and agents, never command wrappers. Before applying, the CLI and the TUI say whether each selected reader skipped the copy or made one because a setting stopped the share.

Evidence:

- `python3 -m unittest discover -s tests` — 329 passed (308 before this change).
- `python3 scripts/validate.py` — ok, 0 warnings.
- `shellcheck scripts/install.sh` — nothing to report (koalaman shellcheck 0.10.0; it is not on `PATH` on this machine).
- Scratch HOME, `python3 scripts/install.py --yes --harness claude,grok --offline`: printed `Grok CLI: 11 skill(s) not copied to <home>/.grok/skills; it already reads them from <home>/.claude/skills (Claude Code).` `--status` shows `= via Claude Code` in the Grok CLI column. `grok inspect --json` listed the 11 toolkit skills once, all with source type `user`.
- Fresh HOME with `GROK_CLAUDE_SKILLS_ENABLED=false`: printed `Grok CLI: 11 skill(s) copied to <home>/.grok/skills; it does not read <home>/.claude/skills (GROK_CLAUDE_SKILLS_ENABLED=false).` Both skills directories had 11 links.

Not delivered: nothing in the goals. Ticket 0001 stays out of scope.

## Closure

Closed 2026-10-04. Outcome: done. The user confirmed closure; the changes stay uncommitted for a separate review.

Follow-ups: none. Ticket 0001 stays out of scope and was not opened by this plan.
