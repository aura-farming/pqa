---
name: perturbation-operators
description: Use when a loop gate needs its perturbation operator applied concretely.
---

# Perturbation Operators

The PA operators are the mechanism at each gate — the forcing moves that stop the loop
from being five names for "think about it." Each gate has exactly one operator; if the
prompt at a gate does not visibly invoke its operator, the gate is broken.

| Gate | Operator | What it forces |
|---|---|---|
| frame-load | P-collapse | name the rigid assumption baked into the task |
| spawn (branch N-1) | P-reframe | one branch refuses the obvious frame entirely |
| adversary | P-deepen | attack what the verifier cannot catch |
| pre-collapse | P-relativize | hold survivors as both-possibly-correct until evidence selects |
| precipitate | P-name | crystallize the winner and every death reason verbatim |

## The operators, concretely

**P-collapse (frame-load).** Every task statement carries an implicit answer-shape.
Name it in one sentence, then surface what holds if it's wrong. "Build a rate limiter"
assumes one tenant; "refactor this 800-line file" assumes the file should be smaller;
"add a retry" assumes the upstream is flaky rather than a real bug being masked. The
named assumption is the first branching axis — nothing downstream recovers it if
skipped.

**P-reframe (spawn).** If the obvious answer is X, branch N-1 builds the best non-X.
Not a twist on X, not X-plus-config — a refusal of X's frame. Token bucket → queue
with backpressure that pushes rejection to the producer. Retry with backoff → typed
error and no retries; the caller decides. The verifier still gates whether the bet
pays; the operator only guarantees the bet is placed.

**P-deepen (adversary).** Refuse the surface answer. Tests/types/lint are the easy
layer; P-deepen asks the question the branch silently answered: what input
distribution did it assume? Which boundary does no test exercise? What does its
failure mode destroy? A P-deepen pass that restates lint output is a broken gate.

**P-relativize (pre-collapse).** Hold every surviving branch as simultaneously
possibly-correct and possibly-noise; never declare from inside. Rank only on the
evidence tuple (findings resolved, coverage, non-incremental); prose quality is not
evidence. The engine's `select_survivor` is this operator made executable.

**P-name (precipitate).** The winner gets a one-line name ("backpressure beats
rejection for bursty ingest") and every loser gets its verbatim death reason. Unnamed
insight dissolves; paraphrased death reasons don't retrieve. This is the write path of
the whole learning moat — `record_precipitate`, `record_failure`, signal outcomes.

## Worked example

Run: "make the nightly export faster."

1. *P-collapse:* assumption — "the export is slow because the query is slow." If
   wrong: it is slow because it exports rows nobody reads.
2. *P-reframe (b2):* obvious is "optimize the query"; the non-X is "export the delta
   only, backfill on demand" — a different data contract, not a faster same-contract.
3. *P-deepen:* b0 (indexed query) assumes row count grows linearly; finding — the
   join fans out quadratically on the tenants table, and no test exceeds 100 rows.
4. *P-relativize:* b0 verified 88%, resolved 2/3 findings; b2 verified 85%, resolved
   3/3 — both held live until the tuple ranks b2 first on findings; coverage never
   consulted.
5. *P-name:* precipitate "delta-export: the fastest query is the one not run"; b0
   death `adversary: join fan-out quadratic on tenants — no test exceeds 100 rows`.

Five gates, five visible moves. Any gate where you cannot point at the operator's
output artifact is a gate that ran on vibes.

## Anti-patterns

- **Name-dropping.** Writing "P-deepen:" above a shallow review is not applying the
  operator. Each move must produce its artifact: the assumption sentence, the non-X
  branch, the verifier-blind finding, the evidence ranking, the verbatim names.
- **Wrong gate.** P-reframe at collapse (re-opening the choice after evidence lands)
  or P-relativize at spawn (hedging generators toward the middle) inverts the loop.
- **P-collapse as criticism.** The point is the assumption's negation space — what
  holds if it's wrong — not complaints about how the task was phrased.
- **P-name as summary.** A paragraph is not a name. One line a future search can hit,
  or the insight dissolves.
- **Operator theatre on a decide-ask.** In decide mode only frame collision and one
  judge pass run; staging all five operators on a question is a scale-gate violation.
