# Theme: project conventions

Check that the code follows the rules this project has written down and the
patterns it consistently uses.

Sources, in order of authority:
1. Guidance files: AGENTS.md, CLAUDE.md, CONTRIBUTING.md, docs on
   conventions or architecture, linters and formatter configs.
2. Consistent patterns in the surrounding code: structure, naming, error
   handling, logging, test layout, dependency choices.

Look for:
- Explicit rules in guidance files that the change breaks. Quote the rule
  and where it lives.
- New code that solves a problem differently from how the rest of the
  codebase solves it (another HTTP client, another logging style, another
  error type) without a reason.
- Files placed in the wrong layer or folder for this project's structure.
- Public API, naming or versioning rules not followed.

Do not flag:
- Rules that apply to other parts of the repository (a guidance file in a
  subfolder applies only there).
- Your own preferences where the project has no rule and no consistent
  pattern.
- What the project's linters and formatters already enforce.
