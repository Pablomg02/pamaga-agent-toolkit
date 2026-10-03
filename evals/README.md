# Evals

One file per skill, `evals/<skill-name>.json`, describing how the skill should
behave and when it should (and should not) be loaded. Use them whenever you
change a skill, to check that the change did not break what already worked.

`scripts/validate.py` checks that every skill has a file and that it follows
the schema below. It does not run the evals: running them needs a model.

## Format

```json
{
  "skill_name": "make-plan",
  "evals": [
    {
      "id": 1,
      "prompt": "A realistic request, as the user would type it.",
      "expected_output": "What a good run produces, in one or two sentences.",
      "files": [],
      "expectations": [
        "One observable, checkable behaviour per line"
      ]
    }
  ],
  "trigger_evals": [
    {"query": "a request that should load the skill", "should_trigger": true},
    {"query": "a near miss that should not", "should_trigger": false}
  ]
}
```

- `evals` test **behaviour**: given the prompt, does the agent follow the
  workflow? Expectations are things a grader can check in the transcript or
  the resulting files ("creates the folder with plans.py new", not "does a
  good job").
- `trigger_evals` test the **description**: would an agent pick this skill
  for that request? The most useful negatives are near misses that belong to
  a neighbouring skill (`make-plan` vs `make-roadmap`, `deep-review` vs
  `find-bug`), not unrelated requests.
- `files` lists fixture paths, relative to the repository root, that the
  eval needs (for example a sample repository with a `plans/` folder).

The format is the one used by Anthropic's `skill-creator` skill, so the same
cases can be fed to it.

## Running them

**By hand.** Start a fresh session in a test repository with the toolkit
installed, send each `prompt`, and tick off the `expectations`. For the
trigger cases, send each `query` and note whether the skill was loaded.

**With skill-creator (Claude Code).** Ask it to evaluate or improve a skill
of this toolkit and point it to the matching eval file. It can run the
behaviour cases with and without the skill, grade the expectations, and use
`trigger_evals` to tune the description. It expects the cases at
`<skill>/evals/evals.json`; give it the path to this file instead, or copy it
there for the run and delete it afterwards (eval files are not installed with
the skills).

## Writing good cases

- Use the way you actually phrase requests, including vague ones ("review my
  changes", "it doesn't work").
- Cover the edges the skill must handle: missing inputs (no plan folder),
  requests that are too small or too big, resumes, the user already giving
  every parameter.
- When a skill misbehaves in real use, add the case here before fixing the
  skill.
