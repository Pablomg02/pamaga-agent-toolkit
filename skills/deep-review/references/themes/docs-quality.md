# Theme: documentation quality

Judge the documentation that comes with the code: docstrings, comments,
README sections, API docs, changelogs and help texts that the change adds
or touches.

Look for:
- Public functions, classes, endpoints, CLI options or config keys added
  without the documentation the project normally provides for them.
- Comments that restate the code instead of explaining why, or that are
  missing where the code is non-obvious (a workaround, an invariant, a
  performance trick, a security reason).
- Documentation that is wrong about what the new code does: parameters,
  return values, errors raised, defaults, side effects.
- Examples that would not run: wrong names, missing imports, outdated
  signatures.
- User-facing changes with no changelog or release note, if the project
  keeps one.

Do not flag:
- Missing docs on private, trivial or self-explanatory code.
- Wording and grammar, unless it changes the meaning.
- Documentation elsewhere in the repository that the change does not affect
  (the outdated-docs reviewer covers that).
