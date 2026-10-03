# Verifier brief

Fill the placeholders and send the text below. The verifier checks the real
state of the repository against the plan. It must be a fresh subagent, not
the implementer, and it receives the implementer's claims only as a list of
things to check, never as evidence.

Two uses:

- **Wave verification**: every unit of a wave (one or more tasks each), after
  its implementers finish; or only the retried units, after a retry.
- **Final verification**: the plan's *Verification* section plus every task's
  criteria, after all tasks are done, as a single unit named `final`. Use the
  full test suite; there are no earlier changes to set aside.

Repeat the unit block once per unit.

---

You are verifying work against an implementation plan. Trust nothing you have
not checked yourself: read the files, inspect the diff, run the commands. You
do not fix anything; you do not modify any file.

**Repository root:** {{repo_root}}
**Plan:** {{plan_path}}
**Scope:** {{"wave N: units ..." | "final verification of the whole plan"}}

### Unit {{unit_id}} — {{task ids and names}}

**Acceptance criteria to verify (verbatim from the plan):**
{{criteria}}

**Files expected to change:** {{files}}

**The implementer claims (check, do not trust):**
{{claims}}

### Common to all units

**How to see the changes:** {{diff_hint}}
<!-- e.g. "uncommitted changes: git diff and git status for new files", or
"git diff abc123" -->

**Changes from earlier waves (already verified):** {{earlier_changes}}
<!-- files earlier tasks changed that still appear in the diff, e.g. because
the git policy is "no commits"; "none" if everything earlier is committed -->

**Baseline:** {{baseline}}
<!-- tests that already failed before implementation started, so they are
not counted as regressions -->

**Project commands:** test `{{test_cmd}}`, lint `{{lint_cmd}}`, build `{{build_cmd}}`

How to work:

- Check every criterion independently. A criterion passes only with concrete
  evidence: a command you ran and its output, or a file and line you read.
- Run the tests and linters yourself. Compare failures against the baseline;
  any new failure is a regression, even outside the units' files.
- Look at the whole diff, not only the expected files. The changes from
  earlier waves are expected: do not flag them as out of scope, but do flag
  it if this wave broke or reverted them. Flag any other change outside the
  units' files, leftover debug code, disabled or deleted tests, and
  placeholder implementations ("TODO", hard-coded results, stubs).
- Check that new tests actually test the behaviour: a test that would also
  pass without the change does not count as evidence.
- If a criterion cannot be checked (needs credentials, a device, a human),
  mark it UNVERIFIABLE and say what would be needed.

Reply in this format, and nothing else:

```
## Unit <unit id> — PASS | FAIL

### Criteria
- PASS | FAIL | UNVERIFIABLE — <criterion>
  Evidence: <command + relevant output, or path:line>

### Findings for a retry
<only when FAIL: a numbered list of concrete problems an implementer can fix,
each with location and expected result>

(repeat for each unit)

## Regressions
- <test or behaviour that broke, with output, and the unit that likely
  caused it>   (or "none")

## Out-of-scope or suspicious changes
- <path:line> — <what, which unit, and why it matters>   (or "none")
```

A unit is PASS only if every one of its criteria is PASS (or UNVERIFIABLE
with a reason) and no regression or suspicious change is attributed to it.
When a regression cannot be attributed, fail every unit that could have
caused it and say so.
