---
description: Opt-in isolation for agents working on the same repository at once - each one works on its own branch in its own git worktree and registers on a shared board (.git/agent-work/) that shows who is doing what, flags overlapping paths and stale sessions, and integrates early. Use only when the user explicitly asks for it - mentions several agents or sessions working on the repository at the same time, asks to work in a separate worktree or isolated branch, asks who else is working here, or names this skill. Not for ordinary edits, even large ones.
---

Load and follow the `concurrent-work` skill. $ARGUMENTS
