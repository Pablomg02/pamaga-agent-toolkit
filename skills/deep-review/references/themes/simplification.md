# Theme: simplification and maintainability

Find code that is harder to understand or change than it needs to be.

Look for:
- Duplication: logic copied instead of reused, especially when a helper
  already exists in the codebase (name it).
- Unnecessary complexity: abstractions with a single use, configuration
  nobody sets, layers that only forward calls, premature generalisation.
- Dead code: unused functions, parameters, imports, flags, branches that can
  never run, commented-out code.
- Confusing code: misleading names, deep nesting that early returns would
  flatten, long functions doing several things, boolean parameters that hide
  meaning.
- Leaky responsibilities: modules reaching into each other's internals,
  business logic in the wrong layer.

For each finding, propose the simpler version concretely. Do not flag:
- Matters of taste where the existing code is clear enough.
- Large refactors unrelated to the reviewed change; mention at most one as
  `low` if it really blocks maintainability.
