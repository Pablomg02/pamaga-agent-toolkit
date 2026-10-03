# pamaga-agent-toolkit

How to write skills, commands and agents here, and the checks to run before
committing, are in [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Branches

Day-to-day work goes on `dev`: push there freely. When a change is ready,
open a PR from `dev` to `main`. PRs run the checks, and merging to `main`
cuts the release. Keep `main` releasable.

`main` is protected: no direct pushes (admins included), only PRs whose
four `check` jobs pass. The repository allows only merge commits; never
re-enable squash or rebase merging: they rewrite the `dev` commits, so `dev`
stops containing the released tags and loses the `[patch]` markers (see
Versions). After the merge, bring `dev` up to `main`
so the next work starts from the release:
`git switch dev && git pull && git merge --ff-only origin/main && git push`.

## Versions

Releases from `main` are semver tags `0.MINOR.PATCH` (`0.1.0`, `0.2.0`...).
The `release` job in `.github/workflows/ci.yml` turns every push to `main`
that passes CI into the next version, computed by `scripts/next_release.py`:
`MINOR` by default, or `PATCH` when a commit subject since the last release
contains `[patch]`. Release notes list
the commits since the previous release. The major stays `0` while the
toolkit is young; `1.0.0` will mark the stable interface.

The version is chosen when committing, and the choice is the user's:

- `MINOR` (no marker): new or changed skills, commands, agents or installer
  behaviour. This is the default.
- `PATCH`: only fixes, typos and docs that change no behaviour. Put
  `[patch]` in the commit subject (the first line; case does not matter),
  e.g. `Fix typo in ship-work [patch]`.

Add `[patch]` only when the user asks for it. One `[patch]` anywhere since
the last release makes the whole next release a `PATCH`, even if other
commits add features, so if a `[patch]` commit is already waiting on `dev`
and you add a feature, tell the user.

`dev` has no tags and no releases: a dev clone's version is its commit. The
installer labels it `0.2.0+3 (dev)` when it is three commits past `0.2.0`,
`dev (abc1234)` when no release is reachable, and compares `origin/dev` with
the clone to say when to pull. A clone on `main` only hears about newer
stable releases.

Never create, move or delete version tags or releases by hand, and do not
write version numbers into files: the tag is the only source of truth.
