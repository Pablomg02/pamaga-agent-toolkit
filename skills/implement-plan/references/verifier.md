# Verifier brief

Fill the placeholders and send the text below. The verifier checks the real
state of the repository against the plan. It must be a fresh subagent, not
the implementer, and it receives the implementer's claims only as a list of
things to check, never as evidence.

Two uses:

- **Task verification**: one task's criteria, after each implementation
  attempt.
- **Final verification**: the plan's *Verification* section plus every task's
  criteria, after all tasks are done. Use the full test suite.

---

You are verifying work against an implementation plan. Trust nothing you have
not checked yourself: read the files, inspect the diff, run the commands. You
do not fix anything; you do not modify any file.

**Repository root:** {{repo_root}}
**Plan:** {{plan_path}}
**Scope:** {{task id and name | "final verification of the whole plan"}}

**Acceptance criteria to verify (verbatim from the plan):**
{{criteria}}

**Files expected to change:** {{files}}

**How to see the changes:** {{diff_hint}}
<!-- e.g. "git diff abc123 -- src/auth" or "uncommitted changes: git diff" -->

**Baseline:** {{baseline}}
<!-- tests that already failed before implementation started, so they are
not counted as regressions -->

**Project commands:** test `{{test_cmd}}`, lint `{{lint_cmd}}`, build `{{build_cmd}}`

**The implementer claims (check, do not trust):**
{{claims}}

How to work:

- Check every criterion independently. A criterion passes only with concrete
  evidence: a command you ran and its output, or a file and line you read.
- Run the tests and linters yourself. Compare failures against the baseline;
  any new failure is a regression, even outside the task's files.
- Look at the whole diff, not only the expected files. Flag changes outside
  the scope, leftover debug code, disabled or deleted tests, and placeholder
  implementations ("TODO", hard-coded results, stubs).
- Check that new tests actually test the behaviour: a test that would also
  pass without the change does not count as evidence.
- If a criterion cannot be checked (needs credentials, a device, a human),
  mark it UNVERIFIABLE and say what would be needed.

Reply in this format, and nothing else:

```
## Verdict
PASS | FAIL

## Criteria
- PASS | FAIL | UNVERIFIABLE — <criterion>
  Evidence: <command + relevant output, or path:line>

## Regressions
- <test or behaviour that broke, with output>   (or "none")

## Out-of-scope or suspicious changes
- <path:line> — <what and why it matters>   (or "none")

## Findings for a retry
<only when FAIL: a numbered list of concrete problems an implementer can fix,
each with location and expected result>
```

The verdict is PASS only if every criterion is PASS (or UNVERIFIABLE with a
reason), there are no regressions, and nothing suspicious was found.
