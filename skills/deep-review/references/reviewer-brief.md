# Reviewer brief

Send one reviewer per theme. Fill the placeholders, paste the full content of
the theme file (`themes/<theme>.md`) where indicated, and send the text below.

---

You are reviewing code for one theme only. Other reviewers cover the other
themes, so stay inside yours. You do not modify any file.

**Repository root:** {{repo_root}}

**Scope:** {{scope_description}}
<!-- e.g. "uncommitted changes plus branch feature/x vs main (14 files)",
"the folder src/billing/", "the whole repository" -->

**Changed files / files to review:**
{{file_list}}

**Diff:** {{diff_path_or_command}}
<!-- a file with the unified diff, or the git command that produces it;
"not applicable" when reviewing paths or the whole repo -->

**Project guidance files:** {{guidance_files}}
<!-- AGENTS.md, CLAUDE.md, CONTRIBUTING.md, docs/CONVENTIONS.md... or "none" -->

**What the change is for (if known):** {{intent}}

## Your theme

{{theme_file_content}}

## How to work

- Read the diff, then the full files around it: a change is only correct in
  its context. Follow calls into other files when the theme needs it.
- When reviewing a diff, focus on the changed lines and the code they
  interact with. Report a pre-existing problem only if it is serious, and
  mark it `pre-existing`.
- When reviewing paths or the whole repository, prioritise by risk: entry
  points, code that handles external input or money or data, complex and
  recently changed modules. Say what you did not get to.
- Every finding needs evidence you saw: a file and line, and for bugs a
  concrete scenario (input or state → wrong result). If you cannot build the
  scenario, it is not a finding.
- Prefer few, real findings over many speculative ones. An empty list is a
  valid result.
- Do not report what a linter or compiler in this project already catches,
  formatting, or personal taste.

## Report

Reply in this format, and nothing else:

```
## Findings

### <short title>
- Theme: {{theme}}
- Severity: critical | high | medium | low
- Confidence: high | medium
- Location: <path:line or path:start-end>
- Evidence: <what the code does, quoting the relevant line>
- Impact: <concrete scenario: input/state → consequence>
- Fix: <specific change>
- Pre-existing: yes | no

## Not covered
<what you could not review and why, or "nothing">
```

Severity:
- **critical**: data loss or corruption, security breach, crash or wrong
  result on a main path.
- **high**: a bug in a realistic scenario, a significant performance
  regression, a missing test for risky logic.
- **medium**: an edge-case bug, misleading documentation, a maintainability
  problem likely to cause bugs.
- **low**: a worthwhile improvement with limited impact.
