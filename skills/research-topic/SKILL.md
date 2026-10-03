---
name: research-topic
description: Investigate a question without changing any code - how something works in this repository, whether a library or approach fits, what the options and trade-offs are - and answer with evidence and sources. Runs single-agent or multi-agent (parallel explorer and researcher subagents) as the user chooses, and saves the report only if asked. Use when the user asks to research, investigate, explore, compare or find out something ("can we use X?", "how does Y work here?", "what are the options for Z?", a spike) before deciding anything. Not for planning a change (make-plan), debugging a known failure (find-bug) or reviewing code (deep-review).
---

# Research a topic

Answer a question with evidence, and change nothing. The deliverable is an
answer the user can decide on: what is true, how sure we are, and what it
means for them. Investigating without the pressure to build something keeps
the conclusion honest; when a decision is made, the report feeds `make-plan`
or `new-ticket`.

## 1. Frame the question

Restate the question in one or two sentences, with what the answer will be
used for (a decision, a plan, curiosity) and the constraints already known
(versions, platform, licences, budget). If the question is vague, split it
into the concrete sub-questions that would answer it and show them.

Then settle two things, unless the user already said:

| Choice | Options |
| --- | --- |
| Mode | **Single agent**: you investigate yourself, in order. Best for one focused question or a small repository. **Multi agent**: one helper subagent per independent sub-question, in parallel. Best when there are several independent questions, or code and web research at once. |
| Output | **Chat only** (default): the report in the conversation. **Saved**: also written to a file (see step 4). |

Ask both in one batch, with your recommendation first and why (for example
"multi agent: three independent questions"). If the harness has no
subagents, say so and work single agent.

## 2. Investigate

**Never change the project.** Read files, search, list, and run read-only
commands (tests, `--help`, version queries). If a question needs an
experiment (a snippet, a benchmark, installing a package), do it in a
temporary folder outside the repository and say so in the report. Never edit
tracked files, commit, or change the environment of the project.

**Single agent.** Work through the sub-questions in order. For each one, look
at the primary evidence (the code, the official docs, the spec), and stop
when it is answered with enough confidence to decide.

**Multi agent.** Launch one helper per independent sub-question, in parallel
(up to four at a time), with your harness's task tool and its
general-purpose agent (`general-purpose` in Claude Code, `general` in
opencode):

| Helper | When | Brief |
| --- | --- | --- |
| Repository explorer | How the existing code works, where something lives, conventions, commands. | `references/repo-explorer.md` |
| Researcher, `docs` mode | Libraries, APIs, versions, limits, known issues. | `references/researcher.md` |
| Researcher, `literature` mode | Standards, papers, established practice. | `references/researcher.md` |

Fill every placeholder: a helper knows only its brief. Give each one a
narrow question, not the whole topic. When they report, read the key
evidence yourself before relying on it; their summaries point to the
evidence, they are not the evidence. If their answers raise a new question,
run another round; stop when another helper would not change the answer.

In both modes, when sources disagree, report the disagreement instead of
picking silently, and never cite a file, URL or fact you have not seen.

## 3. Report

Answer in the user's language, in this shape:

```
## Answer
<direct answer and recommendation, 3-10 lines>

## Findings
- <finding> — <evidence: path:line or source [n]>

## Options compared        (only if the question is a choice)
| Option | Pros | Cons | Fit for our constraints |

## Confidence and gaps
<high / medium / low, what was not checked, and what would raise it>

## Sources                 (only if there are external sources)
1. <title> — <author or publisher>, <date> — <url>

## Next steps
<what the user could do with this: a plan, a ticket, nothing>
```

Lead with the answer, not the process. Keep it as short as the question
allows.

## 4. Save it, if asked

- If the research is for an existing plan, roadmap or ticket, write it to
  `research/<slug>.md` inside that folder (load the `plans-convention` skill
  to find it) and link it from the plan.
- Otherwise write `docs/research/<YYYY-MM-DD>-<slug>.md`.

Saved reports are in English, with the question as the title and the date of
the research, because sources age. Report the path in one line.

## 5. Hand off

Offer what fits, and do nothing else: `make-plan` if the answer leads to a
change, `new-ticket` to keep it for later, `save-learning` if the answer is
a reusable lesson. Do not start implementing.

## Red flags

- Editing a project file, even "just to try something".
- An answer without evidence, or a URL you did not open.
- Launching helpers for a question you could answer with one search or one
  file read.
- Giving helpers the whole topic instead of one narrow question each.
- Burying the answer under a narrative of what you did.
