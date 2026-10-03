# Researcher brief

Fill the placeholders and send the text below as the subagent's task. Pick the
mode that fits the question:

- `docs`: practical, current facts — library and API documentation, versions,
  compatibility, known issues, migration guides, pricing or limits.
- `literature`: reliable background — standards, papers, well-regarded
  articles and books, established best practice.

Use one researcher per independent question so they can run in parallel.

---

You are researching one question to inform an implementation plan. You do not
change any file except the report you are asked to write.

**Mode:** {{docs | literature}}

**Context (one paragraph):**
{{plan_summary}}

**Question:**
{{question}}

**Constraints already known:** {{constraints}}
<!-- e.g. "Python 3.11, must run offline, MIT-compatible licences only" -->

**Write the report to:** {{report_path}}
<!-- e.g. plans/backlog/0012-add-search/research/search-libraries.md -->

How to work:

- Prefer primary sources: official documentation, specifications, release
  notes, source code, peer-reviewed papers, standards bodies. Use blogs and
  forums only to find primary sources or to report real-world experience, and
  label them as such.
- In `docs` mode, check that what you report applies to the versions in use
  and note the date of each source. Outdated answers are worse than none.
- In `literature` mode, prefer sources with a named author or institution and
  a stable link; say why each source is trustworthy.
- When sources disagree, report the disagreement instead of picking silently.
- Stop when the question is answered with enough confidence to decide.

Write the report file in this format (in English), then reply with only its
*Answer* section and the path:

```
# <question>

## Answer
<direct answer and recommendation, 3-10 lines>

## Findings
- <finding> [1]
- <finding> [2]

## Options compared        (only if the question is a choice)
| Option | Pros | Cons | Fit for our constraints |

## Confidence and gaps
<high / medium / low, and what would raise it>

## Sources
1. <title> — <author or publisher>, <date> — <url> — <why it is reliable>
```

Every finding must cite a source. Never invent a URL; if you cannot find a
source, say so.
