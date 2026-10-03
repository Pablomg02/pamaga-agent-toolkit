---
description: Code review at the depth the change deserves - a quick review by the agent itself, one generalist reviewer subagent, or one reviewer per theme (bugs, security, performance, tests, simplification, conventions, design, documentation) with independent validators. Picks the themes from what actually changed, asks the user for the depth when the change is not trivial, reports only findings that survived a check, then proposes to fix the small ones directly and asks whether to fix the large ones or plan them with make-plan, fixing with tests and leaving the changes uncommitted. Use when the user asks for a code review, audit or second opinion of changes, a branch, a PR, a folder or the whole repository, or asks to look for bugs, optimisations or outdated docs in existing code. Not for debugging a known failure (find-bug) or reviewing a plan.
---

Load and follow the `deep-review` skill. $ARGUMENTS
