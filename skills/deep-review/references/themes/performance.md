# Theme: performance

Find code that will be measurably slow, wasteful or unable to scale with
realistic data, and clear optimisation opportunities.

Look for:
- Algorithmic complexity: nested loops over collections that grow, repeated
  linear searches that should be a map or set, sorting inside loops.
- I/O patterns: N+1 queries, queries or HTTP calls inside loops, missing
  batching or pagination, reading whole files or tables into memory, missing
  indexes for new queries.
- Repeated work: recomputing the same value, re-parsing, re-compiling
  regexes, redundant serialisation, cache misses caused by the change.
- Memory: unbounded growth, large copies, retaining references, loading data
  that is never used.
- Concurrency: blocking calls on async paths or UI threads, sequential work
  that is trivially parallel, lock contention.
- Hot paths: work added to code that runs per request, per frame or per
  item.

For each finding, estimate the scale at which it matters ("with 10k rows this
does 10k queries"). Do not flag:
- Micro-optimisations with no measurable effect at the project's scale.
- Code that runs once at startup or in tooling, unless it is really slow.
- Optimisations that would make the code much harder to read for a small
  gain; mention the trade-off if you report it.
