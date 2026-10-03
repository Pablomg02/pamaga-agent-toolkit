---
name: find-bug
description: Systematic debugging when the cause is not obvious - reproduce the problem, narrow it down with experiments, find the root cause, then fix it with a regression test; no blind patches. Use when something crashes, hangs, gives wrong results, a test fails or is flaky, behaviour changed after an update, or the user asks to debug, find a bug or explain why something happens. Not for typos or errors whose fix is evident from the message, nor for reviewing code with no known failure (deep-review).
---

# Find a bug

A fix without a root cause is a guess. Guesses hide the bug, move it, or add
a second one. Work like an experiment: observe, form a hypothesis, test it,
and only change the code once you can explain the failure from cause to
symptom.

If the user only asked *why* something happens, stop after step 5 and
propose the fix. Otherwise go through to the end.

## 1. Pin down the symptom

Write down, in one place:

- what happens and what should happen instead, with the exact error, output
  or stack trace;
- where: command, input, environment, versions;
- since when, and what changed around then (commits, dependencies, config,
  data);
- how often: always, sometimes, only under load, only on one machine.

Ask the user only for what you cannot find out yourself.

## 2. Reproduce

Get a reliable reproduction before anything else, ideally as a failing
automated test, otherwise as a single command. Then make it smaller: remove
input, steps and configuration until everything left is necessary.

If it cannot be reproduced, do not fix blind. Gather evidence instead (logs,
traces, environment differences between where it fails and where it does
not), add targeted logging if needed, and tell the user what would let you
reproduce it.

## 3. Locate

Narrow the search space with cheap, decisive moves. Read
`references/techniques.md` for how to apply each one.

- Follow the stack trace or error to the code that produces it; read it.
- Compare a working case with a failing one and shrink the difference.
- If it used to work, bisect the history (`git bisect run` with the
  reproduction).
- Bisect the code path: check the state halfway through; keep the half that
  is wrong.
- Instrument: log or assert the values you assume, at the boundaries where
  they change.

## 4. Hypothesise and test

List the plausible causes, most likely first. For each one, design an
experiment whose result would rule it out, run it, and record the outcome in
a short log (hypothesis → experiment → result). Test one hypothesis at a
time; changing several things at once tells you nothing.

## 5. Root cause

You have the root cause when you can explain the full chain from the
original defect to the observed symptom, and the reproduction confirms each
link. Then ask:

- Why did the tests not catch it?
- Does the same mistake exist elsewhere? Search for the pattern.
- Is this the root, or a symptom of something deeper (a wrong assumption, a
  bad interface, missing validation upstream)?

## 6. Fix

1. Write the regression test first (or turn the reproduction into one) and
   watch it fail for the right reason.
2. Make the smallest change that fixes the root cause, not the symptom.
   Catching the exception, adding a retry or special-casing the input are
   symptom fixes unless the analysis shows they are correct.
3. Watch the test pass. Run the whole test suite and compare against how it
   was before your change.
4. Remove temporary logging and debugging code.

If the proper fix is large (changes an interface, touches many files, needs
a migration), stop and propose it to the user; offer `make-plan` for it and,
if they want one, a minimal safe mitigation in the meantime.

**Three strikes.** If three fixes in a row fail, stop changing code. Your
model of the problem is wrong: go back to step 3, question each assumption,
and tell the user what you have ruled out.

## 7. Report

- **Symptom**: one line.
- **Root cause**: the chain from defect to symptom, with file and line.
- **Fix**: what changed and why it addresses the cause.
- **Proof**: the regression test, and the suite result.
- **Elsewhere**: other places with the same pattern, fixed or not.
- **Follow-ups**: anything left, offering to capture it with `new-ticket`.
  If the root cause was non-obvious and could bite again elsewhere, offer to
  keep it with `save-learning`.

## Red flags

- Editing code before you can reproduce the problem.
- "Let's try this and see" without a hypothesis the attempt would test.
- A fix that makes the error disappear without explaining it.
- Disabling, skipping or loosening a test to make it pass.
- Leaving debug logging behind.
