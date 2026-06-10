---
name: the-spiral
description: Use when deciding whether to re-enter the loop on a survivor.
---

# The Spiral

A spiral is another co-precipitation round run ON the survivor of the last one — the
precipitate becomes the next round's task. Depth is available but never free: each
round costs a full loop's tokens, and an unbounded spiral is how runs escape their
budgets. The engine enforces the cap; this skill is the judgment about when depth
actually pays.

## The guard (engine-enforced)

- `max_spiral_depth` — config key / `PQA_MAX_SPIRAL_DEPTH`, default 1, validated to
  [0, 5]. Depth 0 disables spirals entirely.
- `pqa.orchestrator.run_pqa(..., spiral_depth=d, max_spiral_depth=m)` aborts with a
  reported (never silent) `aborted=True` RunReport when `d > m` — "a brake is not a
  steering wheel": the budget alone must never be the only thing stopping recursion.
- `spiral_depth` is surfaced in the run report, so nobody mistakes a two-round result
  for a one-shot.

## When to spiral (any one suffices)

- **The precipitate names a new axis.** The winner's one-line name contains a fork the
  run did not explore ("delta-export…" → spiral: what should backfill semantics be?).
- **Collapse was UNVERIFIED but is verifiable.** No suite existed; the survivor's
  shape makes a locked test set writable. Spiraling with the suite in place turns
  judgment into evidence — the highest-value second round there is.
- **Unresolved non-critical findings cluster.** Three high findings pointing at the
  same seam are a frame disagreement for round two.
- **The operator perturbs.** A human checkpoint rejecting the frame or the survivor IS
  the collision the harness cannot generate; their objection seeds the new frame.

## When to stop (any one suffices)

- **Verified survivor, findings resolved.** A clean win does not need a second opinion
  at full-loop prices.
- **Remaining budget < one honest round.** A starved spiral produces underexplored
  branches that die `budget:` — noise in the taxonomy, not learning.
- **The new task re-litigates a recorded death.** If the spiral's frame matches a
  `verifier:`/`adversary:` failure row, the answer already exists; read it instead.
- **It's a decide-ask.** Questions never spiral — the scale gate applies at every
  depth, and "one more loop on it" is the upgrade reflex in disguise.
- **The pull is elegance.** "It verifies but could be prettier" is a refactor for a
  human, not a superposition for the harness.

## Protocol

1. Read the precipitate and run report of the finished round (`.pqa/artefacts/`).
2. Apply the gates above. The default is STOP — depth defaults to 1 for a reason, and
   a spiral is the exception that must argue for itself.
3. If spiraling: the new task is the precipitate's open question stated as a fresh
   one-line ask. Frames load fresh — research may not have changed, but self-eval HAS:
   the survivor is now part of the codebase. Pass `spiral_depth=d+1` and the
   **remaining** budget, never a fresh one — depth competes with breadth for the same
   tokens. The scale gate re-classifies the new ask from scratch: a build run's spiral
   is often a patch run.
4. Journal the chain: the child's report carries its `spiral_depth`; the parent's
   precipitate references the child ("spiraled: see run <id>") so the registry shows
   the lineage.

## Worked example

Run 1 (build): "make nightly export faster" → survivor b2 "delta-export", verified
88%, precipitate "delta-export: the fastest query is the one not run", 420k of 800k
tokens spent. The precipitate's open question: backfill semantics for new consumers.

Gate check: new axis named ✓; remaining 380k ≥ one patch-sized round ✓; no matching
failure row ✓ → spiral approved at depth 1.

Run 2 (spiral, depth 1, budget = the remaining 380k): task "define backfill semantics
for delta-export consumers" — the scale gate classifies it **patch** (2 branches:
backfill-on-subscribe vs lazy-page-on-read). Lazy wins, verified. Total: 2 rounds,
~690k tokens, both inside the original envelope, lineage recorded in both reports.

The counterfactual round 3 ("cursor or offset pagination?") is a decide-ask — one
judge pass at decide economics answers it, and `max_spiral_depth=1` would have refused
a third full loop anyway. Both brakes exist; neither is the steering wheel.

## Anti-patterns

- **Spiraling for elegance.** Verified + resolved = done; beauty is not a branching
  axis.
- **Fresh budgets per round.** Inheriting the remainder is the point — otherwise depth
  is unbounded spend wearing a seatbelt.
- **Silent depth.** A result that hides its spiral depth misrepresents both its cost
  and its confidence.
- **Re-litigating recorded deaths.** The taxonomy exists so round N+1 never pays for
  round N's lesson twice.
- **Defaulting depth up.** If most runs "need" depth 2, the frames or axes at depth 0
  are too shallow — fix the gates, not the cap.
