# Theme: bugs

Find code that produces a wrong result, crashes, hangs or corrupts state.

Look for:
- Logic errors: wrong conditions, inverted checks, off-by-one, wrong operator,
  wrong variable, missing `return` or `break`.
- Unhandled cases: null or empty values, zero, negative numbers, empty
  collections, unicode, very large inputs, timeouts, partial failures.
- Error handling that swallows failures, reports success on error, or leaves
  state half-updated.
- State and concurrency: race conditions, shared mutable state, missing
  locks or awaits, wrong ordering of side effects, stale caches.
- Resource handling: leaks of files, connections or memory; missing cleanup
  on error paths.
- Contract breaks: a changed function whose callers still assume the old
  behaviour, signature or return type; API or schema changes that break
  clients or stored data.
- Type and conversion errors: precision loss, time zones, encodings, integer
  overflow, implicit coercions.

Do not flag:
- Style, naming or structure (other reviewers cover those).
- Issues that need an impossible input given the types and callers you can
  see.
- Hypothetical problems without a concrete failure scenario.
