# pamaga-agent-toolkit

How to write skills, commands and agents here, and the checks to run before
committing, are in [docs/CONVENTIONS.md](docs/CONVENTIONS.md).

## Versions

Every push to `main` that passes CI is released automatically as
`YYYY.MM.DD.N`: the date in Spain (Europe/Madrid) and a counter that starts
at 1 each day (`2026.10.03.1`, `2026.10.03.2`). The `release` job in
`.github/workflows/ci.yml` creates the tag and the GitHub Release.

Never create, move or delete version tags or releases by hand, and do not
write version numbers into files: the tag is the only source of truth.
