# pamaga-agent-toolkit

How to write skills, commands and agents here, and the checks to run before
committing, are in [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Branches

Day-to-day work goes on `dev`: push there freely. When a change is ready,
open a PR from `dev` to `main`. PRs run the checks, and merging to `main`
cuts the release. Keep `main` releasable. Every push to `dev` that passes CI
is tagged as a dev build (see Versions).

## Versions

Every push to `main` that passes CI is released automatically as
`YYYY.MM.DD.N`: the date in Spain (Europe/Madrid) and a counter that starts
at 1 each day (`2026.10.03.1`, `2026.10.03.2`). The `release` job in
`.github/workflows/ci.yml` creates the tag and the GitHub Release.

Every push to `dev` that passes CI is tagged `YYYY.MM.DD.N-dev`
(`2026.10.03.3-dev`) by the same `release` job, with no GitHub Release, so
the Releases page only lists `main`. Stable and dev tags share the same
daily counter, so they sort by time and never collide. Stable release notes ignore
dev tags (`git describe --exclude '*-dev'`). The installer treats a clone on
`dev` as a development build: it says so, recommends the stable release and
offers newer dev builds; a clone on `main` is never told about dev builds.

Never create, move or delete version tags or releases by hand, and do not
write version numbers into files: the tag is the only source of truth.
