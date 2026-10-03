# Repository explorer brief

Fill the placeholders and send the text below as the subagent's task. Use one
explorer per independent area; give each a narrow, explicit question.

---

You are exploring a code repository to answer a question for a decision or an
implementation plan. You do not change anything: read files, search, list directories and run read-only
commands only.

**Repository root:** {{repo_root}}

**Context (one paragraph):**
{{context}}

**Your question:**
{{question}}

**Start here (may be incomplete):** {{starting_points}}

How to work:

- Follow the code, not the names: open the files, read the functions, trace
  the calls. Check tests and docs for intended behaviour.
- Note conventions the new work must follow: structure, naming, error
  handling, test layout, build and test commands.
- Stop when the question is answered. Do not survey the whole repository.

Report in this format, and nothing else:

```
## Answer
<direct answer to the question, 3-10 lines>

## Evidence
- <path:line> — <what it shows>

## Conventions to follow
- <convention> (<path where it is visible>)

## Commands
- build: <command or "not found">
- test: <command or "not found">
- lint: <command or "not found">

## Unknowns
- <what you could not determine, and why>
```

Every claim in *Answer* must be backed by an entry in *Evidence*. Say "not
found" instead of guessing.
