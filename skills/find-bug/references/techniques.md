# Debugging techniques

Pick the cheapest technique that cuts the search space the most.

## Read the evidence first

- Read the whole error and stack trace, from the innermost frame of your own
  code outwards. The first line is often a consequence, not the cause.
- Check the logs just before the failure, not only at it.
- Note exact versions of the runtime, dependencies and OS where it fails.

## Minimise the reproduction

Remove half of the input, configuration or steps; if it still fails, keep the
smaller version, otherwise try the other half. Repeat until nothing can be
removed. A minimal reproduction often makes the cause obvious and becomes the
regression test.

## Differential debugging

When it works in one place and fails in another (machine, branch, version,
input, user), list every difference and eliminate them one at a time, or in
halves. Typical culprits: environment variables, locale and time zone, file
system case sensitivity, dependency versions, data, permissions, caches.

## Bisect the history

When it used to work:

```bash
git bisect start <bad-commit> <good-commit>
git bisect run <command that exits 0 when good, non-zero when bad>
git bisect reset
```

Make the command fast and deterministic; exit with 125 to skip commits that
cannot be tested. For dependency regressions, bisect the lock file or
versions instead.

## Bisect the code path

Pick a point halfway between the input and the wrong output and inspect the
state there. If it is already wrong, the bug is upstream; otherwise
downstream. Repeat. Use a debugger breakpoint, a log line or an assertion.

## Instrument assumptions

Turn every "this must be X here" into an assertion or a log line, at the
boundaries where values cross modules, processes or services. The assumption
that fails is where to look. Remove the instrumentation when done.

## Flaky and intermittent failures

- Run the test many times in a loop and in isolation; record the failure rate.
- Randomise or fix the order of tests to detect shared state.
- Look for time (now, sleeps, time zones), randomness without a seed,
  concurrency, network, and resource limits.
- Increase load or reduce resources to make a race more likely, then fix the
  ordering instead of adding sleeps.

## Performance problems

Measure before changing anything: profile the slow path with realistic data
and fix the biggest cost first. Compare against a baseline after each change.

## Heisenbugs

If observing the bug changes it (logging or a debugger makes it disappear),
suspect timing, uninitialised memory, or optimisation-dependent behaviour.
Use low-overhead observation: counters, ring buffers, core dumps, record and
replay tools.

## Explain it out loud

Write the full path from input to output, step by step, as if to someone who
does not know the code. The step you cannot justify from the code is usually
the bug.
