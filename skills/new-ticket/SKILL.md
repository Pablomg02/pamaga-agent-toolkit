---
name: new-ticket
description: Capture a bug, idea, request or follow-up in a minute as a ticket folder in plans/backlog/, without planning or fixing it. Use when the user says "create a ticket", "add this to the backlog", "note this for later" or "open an issue for this", or to record the follow-ups a review, debugging session or implementation leaves undone. Not for work the user wants done now.
---

# New ticket

A ticket records something worth doing later, with enough context that it
still makes sense in a month. Capturing it should take a minute: this is not
planning. When the time comes, the ticket is implemented directly if it is
small, or promoted to a plan with `make-plan`.

Load the `plans-convention` skill first. `<plans-convention>` below stands
for the folder that skill was loaded from.

## Steps

1. **Gather the essentials**, mostly from the conversation and the code:
   - what: the bug, idea or request in one or two sentences;
   - why it matters, or what triggered it;
   - for a bug: how to reproduce it, expected vs actual behaviour, the
     error, and where it was seen;
   - where in the code, if known (paths, functions);
   - how we will know it is done (one to three acceptance criteria).

   Ask the user only if the *what* or the *why* is unclear. Do not ask about
   the solution; do not investigate beyond a quick look to get the paths
   right.
2. **Check for duplicates**: `plans.py list --status backlog` and
   `--status in-progress`. If an existing ticket or plan already covers it,
   tell the user and offer to add the new information there instead.
3. **Create it**: `python3 <plans-convention>/scripts/plans.py new --type ticket --title "<short imperative title>"`.
   Add `--parent <id>` if it belongs to a roadmap.
4. **Fill `plan.md`**: *Justification* with the what, why and reproduction;
   *Plan* with a first idea of the fix only if one is already known; the
   acceptance criteria. Leave *Implementation*, *Results* and *Closure*
   empty. Write in English.
5. **Report** the id and path in one line.

Several follow-ups at once (for example, the unfixed findings of a review)
are one ticket each, unless they are the same change in several places.

## Title

Short and imperative, describing the outcome: "Fix crash when exporting an
empty note", "Support dark mode in settings". Not "Bug", "Idea about
export", or a sentence copied from an error message.
