---
description: Multi-agent code review - asks for the scope and themes (bugs, security, performance, tests, simplification, project conventions, documentation quality, outdated docs) if not given, runs one reviewer subagent per theme in parallel, and has independent validators discard false positives before reporting. Use when the user asks for a code review, audit or second opinion of changes, a branch, a PR, a folder or the whole repository, or asks to look for bugs, optimisations or outdated docs in existing code. Not for debugging a known failure (find-bug) or reviewing a plan.
---

Load and follow the `deep-review` skill. $ARGUMENTS
