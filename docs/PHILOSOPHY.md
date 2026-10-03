# Philosophy

Why the skills are shaped the way they are. Read this before adding or
changing a skill: a change that fits these ideas belongs here; one that
fights them probably does not.

## You stay the owner

The toolkit exists so that I stay in control of my projects: I understand
what is going on, I learn along the way, and I decide. So every decision
that matters is shown or asked, never taken silently:

- Planning asks until nothing is ambiguous, with a recommendation, and
  records every answer in the plan.
- Implementation leaves the changes uncommitted. I look at them, review
  them, and decide when they are good enough to commit.
- Nothing is pushed, published or deleted without my say.
- Everything the skills produce is plain Markdown in the repository
  (`plans/`, `docs/`), readable without any tool and reviewable in a pull
  request.

## Expensive thinking, cheap typing

Most of the cost of a change is typing it; most of its risk is deciding it.
So the two are split across models:

| Stage | Model | Why |
| --- | --- | --- |
| Plan (`make-plan`) | The best one available | Every design decision is taken here. |
| Implement (`implement-plan`) | A cheap, capable one | It only follows the plan and proves each step. |
| Review (`deep-review`) | The best one again | Fresh eyes on what was actually built, and the fixes it calls for. |

The skills themselves are model-agnostic: the split is a habit, not a
setting. Any stage works with any model, and with one model for everything.

## Safety comes from the contract, not from supervision

A cheap model is safe to implement with when it has nothing left to guess.
The safety does not come from more agents watching it, but from what it is
given and what it must show:

1. **A precise plan.** Exact files, tasks small enough to verify, and
   acceptance criteria that are commands with expected results. No `TBD`,
   no "handle errors properly", no design left to the implementer.
2. **A clear line on decisions.** How to write the code is the
   implementer's choice. Anything that would change the result (behaviour,
   output, what other code sees) and that the plan does not settle is a
   question for the user, not a guess.
3. **Tests first.** Each test is seen failing before the change it covers,
   so it proves something. A baseline of pre-existing failures keeps old
   problems from being blamed on the new work.
4. **Evidence, not claims.** A criterion is met only with a command that
   was run and its output, or a file and line. Criteria are never relaxed
   to get past them.
5. **An independent check of the claims.** The review by a strong model
   re-runs the plan's verification and compares what the implementer
   reported with the diff. Lying about evidence does not survive it.

The safeguards sit at the ends (a good plan before, a solid review after),
not in a crowd of agents in the middle.

## Few agents, on purpose

Subagents cost tokens and lose context: each one starts knowing only its
brief. They are used only where that trade pays off:

- **Implementation** runs as a single agent by default. Subagents only
  when the plan splits the work into substantial packages with disjoint
  files and fixed interfaces.
- **Review** has the depth the change deserves: a quick self-review for a
  small change, one generalist reviewer, or one reviewer per theme for
  risky code. Themes come from what actually changed.
- **Research and planning** investigate alone by default; helpers only for
  independent questions that each need real digging.
- **A plan critic** is offered only for large or risky plans.

No verifier watches the implementer. The tests, the evidence and the final
review do that job for less.

## Simple over complete

These skills nudge, they do not cage. Each one does one job, says why its
rules exist (a model that knows the reason handles the case the rule did
not foresee), and offers the next step without taking it. An instruction
that adds ceremony without value, closes options for no reason, or
duplicates another skill does not belong here.
