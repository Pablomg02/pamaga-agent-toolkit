# Theme: outdated documentation

Find documentation anywhere in the repository that the reviewed code has made
false. The code is the source of truth; the question is what now lies about
it.

How to work:
1. List what the code changes from the outside: names of functions, classes,
   commands, flags, endpoints, config keys, environment variables, files and
   paths, defaults, behaviours, supported versions.
2. Search the repository for each of them: README files, `docs/`, comments
   and docstrings in other files, examples, tutorials, help texts, CLI usage
   strings, config samples, CI files, AGENTS.md and CLAUDE.md.
3. Read each hit and decide whether it is still true.

When reviewing paths or the whole repository instead of a change, compare the
documentation against the current code directly: commands and examples that
no longer work, options that no longer exist, behaviour described
differently from what the code does.

Report each outdated statement with its location, what it says, what is true
now (with the code location that proves it), and the corrected text. Do not
flag:
- Historical documents that describe the past on purpose (changelogs,
  decision records, closed plans).
