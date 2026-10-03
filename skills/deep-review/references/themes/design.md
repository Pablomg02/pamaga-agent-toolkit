# Theme: design and decisions

Check that the change is built the right way, not only that it works: the
approach, where the code lives, and the decisions behind it.

Sources: the plan or PR description if there is one (its *Approach* and
*Decisions*), architecture or decision documents, and how the rest of the
codebase is structured.

Look for:
- Departures from the plan or recorded decisions that nobody approved, or
  plan decisions the change silently ignored.
- An approach that will not hold up: it couples modules that were
  independent, puts logic in the wrong layer, duplicates something that
  already exists, or will not scale to the cases the project clearly has.
- Public interfaces (APIs, CLI flags, file formats, schemas, config keys)
  that are hard to change later and are named or shaped inconsistently with
  the rest.
- Decisions with real trade-offs that are not written anywhere a future
  reader would look.

Do not flag:
- A different approach you would have preferred when the chosen one has no
  concrete problem.
- Local code structure inside a function (the simplification theme covers
  that).
- Decisions the plan or the user already took and justified, unless the
  change shows they are wrong.
