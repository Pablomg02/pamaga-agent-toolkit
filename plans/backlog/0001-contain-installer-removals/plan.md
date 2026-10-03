---
id: "0001"
title: "Keep installer removals inside the harness folders"
type: ticket
created: 2026-10-03
---

# 0001 — Keep installer removals inside the harness folders

## Justification

In project scope (`--scope project`) the harness folders (`.claude/`,
`.opencode/`, `.agents/`) and their manifest `.pamaga-toolkit.json` come from
the project checkout. A repository crafted against this installer can make
`--uninstall`, `--update` or a TUI install (which always prunes) unlink or
move files anywhere the user can write, for example in their home.

Found by the deep review of 2026-10-03, and reproduced there with a fake
HOME:

1. A repository commits `.claude/skills -> ../../..` and
   `.claude/.pamaga-toolkit.json` with
   `{"items":{"skill/.ssh":{"mode":"link"},"skill/.bashrc":{"mode":"link"}}}`.
2. Inside it, run `python3 scripts/install.py --uninstall --scope project --offline`.
3. Actual result: `~/.bashrc` (a symlink) is unlinked, and `~/.ssh` is moved
   to `<repo>/.claude/.pamaga-backups/<stamp>/skills/.ssh`, which is inside the
   attacker's working tree. No confirmation is asked, and the printed plan
   shows paths under `.claude/skills/`, which hides where the files really are.
4. Expected: the installer only touches entries inside the real harness
   folder that it can show are its own.

Cause:

- `state._split_key` (`scripts/installer/state.py`, around 361-366) only
  rejects names that contain `/`. On Windows `\` gets through too, so
  `..\..` escapes even without a symlink.
- `scan` turns every manifest key that is not in the catalog into an
  ORPHANED entry (`state.py`, around 196-201).
- `_orphan_from_manifest` and `item_target` build the target with no
  containment check (`state.py`, around 300-324).
- `actions._remove` unlinks symlinks and moves everything else into the
  backup dir (`scripts/installer/actions.py`, around 689-706).

Severity is medium. The attack needs a repository written against this
installer, and the user must run the toolkit's installer in project scope
inside it. Manifests the toolkit writes itself only hold catalog names.

## Plan

First ideas. They need decisions, especially on which orphans may be pruned
at all, so promote this ticket with `make-plan` before implementing it:

- Accept only manifest keys whose name matches the catalog name pattern
  (`^[a-z0-9]+(?:-[a-z0-9]+)*$`), and ignore any other key.
- Before any remove, move or write, check that the `realpath` of the
  target's parent equals the `realpath` of `harness.dir_for(kind)`, and that
  this folder does not leave `realpath(harness.base)`. If either check fails,
  refuse the action.
- Prune an ORPHANED entry only when it is a symlink into the toolkit clone,
  or a copy whose content hash matches the hash in the manifest.

### Acceptance criteria

- [ ] The repro above, as a test with a fake HOME, leaves `~/.bashrc` and
      `~/.ssh` untouched and reports the entries as refused or ignored.
- [ ] Manifest keys with `.`, `..`, `\` or other characters outside the
      name pattern never produce a remove action (unit test on `scan`/`plan_actions`).
- [ ] Existing install, update and uninstall tests still pass.

## Implementation

## Results

## Closure
