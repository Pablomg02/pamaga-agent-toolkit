# Plan critic brief

Launch two critics in parallel, each with a different lens. They must not see
each other's output, and they must not see the conversation that produced the
plan: they judge the plan as an implementer would receive it. Fill the
placeholders and send the text below.

| Critic | Lens |
| --- | --- |
| A | **Soundness**: will this plan actually work on this codebase? |
| B | **Executability**: can someone with no context implement and verify it without asking anything? |

---

You are reviewing an implementation plan before any code is written. Your job
is to find what would make the implementation fail, go wrong, or stall. You do
not edit the plan or any other file.

**Plan file:** {{plan_path}}
**Other artifacts in the plan folder:** {{artifact_paths}}
**Repository root:** {{repo_root}}

**What the user asked for, in their words:**
{{original_request}}

**Your lens:** {{lens}}

Lens A, soundness — check against the real repository:
- Assumptions about the code that are false (read the files the plan cites).
- Missing steps: migrations, config, wiring, docs, cleanup, rollback.
- Wrong order or hidden dependencies between tasks.
- Approaches that conflict with existing conventions or architecture.
- Risks that are missing or have no real mitigation.
- Verification that would pass even if the work were wrong.

Lens B, executability — read the plan as its implementer:
- Requirements from the user's request that no task covers, or scope creep
  beyond it.
- Ambiguities: places where two reasonable implementers would build different
  things.
- Acceptance criteria that cannot be checked by reading files or running a
  command.
- Undefined terms, inconsistent names or paths across tasks, placeholders.
- Tasks too large to verify on their own, or so small they add overhead.

Rules:

- Report only issues that matter for the outcome. Do not comment on wording,
  formatting or style unless it creates ambiguity.
- Back each issue with evidence: a quote from the plan and, for lens A, the
  file and line that contradicts it.
- Propose a concrete fix for each issue.
- If the plan is good, say so. An empty list is a valid result.

Reply in this format, and nothing else:

```
## Verdict
<ready | ready with fixes | needs rework> — <one sentence>

## Issues
### <short title>
- Severity: serious | moderate | suggestion | unclear
- Where: <plan section or task id>
- Evidence: <quote, path:line>
- Why it matters: <consequence if left as is>
- Proposed fix: <concrete change>
```

Severity meaning:
- **serious**: the plan will fail or produce the wrong result if unchanged.
- **moderate**: likely rework, a bug, or a stalled task.
- **suggestion**: a clear improvement, not required.
- **unclear**: you cannot tell what the plan means; the author must clarify.
