# TODO

Planned additions to the toolkit.

## Skills

- [x] **Code review** (`deep-review`) — the agent deploys a set of subagents, each one reviewing
  a specific theme: quality of the code documentation, bugs, outdated
  documentation, and any other theme worth covering.

- [x] **Planning** (`make-plan`) — the agent takes the user's guide of what they want to
  achieve, analyzes the existing code or elements (if any) and examines the
  proposal in detail. To do so it may launch helper subagents: repository
  readers, web searchers gathering information, researchers looking for
  reliable articles and references, etc. Before finishing, the agent returns
  questions to the user to refine the plan. Once there are no doubts left and
  no more subagents are needed, the agent writes an implementation plan (as a
  plan folder following the work organization convention) and invokes two
  independent subagents that analyze the proposal and look for moderate or
  serious flaws, suggestions for improvement, or points left unclear. With
  their feedback, the agent decides which points to apply, ignore, or consult
  with the user.

- [x] **Implementation** (`implement-plan`) — the agent implements what the implementation plan
  describes. Requires an existing plan folder as input; if there is none, it
  says so and stops. Before starting, it makes sure the plan is unambiguous:
  decisions are asked to the user and every clarification is recorded in the
  plan before proceeding. The main agent
  acts as coordinator: it defines each subagent's task (objective, scope and
  paths, acceptance criteria, expected report format) and, once they finish,
  launches a verification agent that checks the real artifacts against the
  plan, not the subagents' summaries. If something failed, the coordinator
  re-invokes the specific task with the verifier's findings, with a retry limit
  (max 2 per task); if it still does not converge, it stops and asks the user.

- [x] **Long-term planning (roadmap)** (`make-roadmap`) — instead of deriving in an
  implementation plan, it produces an over-plan: a plan of something the user
  wants to accomplish over time, from which smaller implementation plans
  derive (the ones handled by the planning skill). It is stored as a plan
  folder too, and should cover milestones, ordering and dependencies, and what
  each derived plan is expected to resolve. It does not invoke anything: it
  only creates the over-plan; derived plans are left for the user to invoke.

- [x] **Work organization** (`plans-convention`) — a short, clear skill defining where plans and
  tickets live in a repository: a `plans/` folder with `backlog/`,
  `in-progress/` and `done/`, and one folder per plan/ticket named
  `<id>-<slug>/` containing a canonical `plan.md` (justification, plan,
  implementation, results, closure) plus any artifacts (research, images,
  generated pages). Plan folders move between the three status folders as work
  progresses. Mega-plans and subplans are top-level plan folders that reference
  each other by id. A small script bundled with the skill computes the next
  free id and checks that an id is not already used.

- [x] **Plan explainer webpage** (`plan-page`) — reads a plan folder and generates a
  self-contained HTML page with a predefined style (single file, inline CSS, no
  external dependencies) explaining what is going to be done: phases, tasks,
  dependencies, acceptance criteria. The page is stored inside the plan folder.
  Invoked on demand, when the user asks for an explanatory page of a plan.
  When a plan changes and its folder already has a generated page, the agent
  reminds the user that the page is out of date and offers to regenerate it; it
  never regenerates it silently.

## Added along the way

- [x] **Debugging** (`find-bug`) — systematic debugging: reproduce, narrow
  down, root cause, fix with a regression test.
- [x] **Quick tickets** (`new-ticket`) — capture a bug or idea in
  `plans/backlog/` without full planning.
- [x] **Validator, tests and CI** — `scripts/validate.py`, `tests/`, GitHub
  Actions on Linux and macOS.
- [x] **Evals** — behaviour and trigger cases per skill in `evals/`.
- [x] **Concurrent work** (`concurrent-work`) — one branch and worktree per
  agent, a shared board of who is doing what, overlap and stale detection.

## Ideas

- [ ] Run the evals for each skill (by hand or with skill-creator) and tune
  descriptions with the trigger cases.
- [ ] `install.sh all` links skills into both opencode and Claude Code, and
  opencode also reads `~/.claude/skills`, so it sees every skill twice.
  Consider skipping opencode's skills folder when installing both.
