---
name: superposition-branching
description: Use when spawning N parallel solution branches that must differ in topology, not style.
---

# Superposition Branching

Spawn N solutions that genuinely coexist as live possibilities before any is chosen.
The point is to stop probability mass pooling on the obvious path: if every branch is
a restyled version of the same design, the run is expensive noise and collapse learns
nothing. Topology — architecture, data model, control flow — is what must differ.

## When to use

- The superpose step of a `build` run (full loop) or `patch` run (2 branches).
- NOT in `decide` mode: questions get frame collision + one judge pass, no generators.
  The scale gate exists precisely so compare/choose asks never pay for a superposition.

## Protocol

1. **Size N from the scale gate, not habit.** `build` → `branches` from
   `pqa.config.load_or_defaults()` (default 3); `patch` → 2, no unknown-scout. Never
   silently upgrade a decide-ask into a build run.
2. **Generate prompts with the engine**, never by hand:
   `pqa.superposition.spawn_prompts(n, base_prompt, disagreement=d, force_non_obvious=n-1)`.
   Each prompt carries one explicit topology axis; the frame disagreement is split
   across branches (even-indexed take the research side, odd-indexed the self-eval
   side) so the spawned branches realize the collision instead of hearing about it.
3. **Reserve branch N-1 for P-reframe.** `force_non_obvious=n-1` inserts the directive:
   if the obvious answer is X, build the best non-X. This is the unknown-scout's branch
   (`pqa-unknown-scout`, model `fable`) — its axis must be disjoint from every sibling's.
4. **Dispatch ALL generators in ONE message** (parallel Task calls, model `fable`).
   Sequential spawning lets branch 2 see the world after branch 1 — convergence by
   contamination. Generators are blind to siblings by design.
5. **Enforce the digest contract.** Every generator writes its payload to
   `.pqa/branches/bN/` (code + `notes.md` stating its assumptions) and returns ONLY:
   `{branch_id, topology_axis, approach (≤3 sentences), files_touched, loc,
   conviction?, basis?}` — hard cap 150 tokens. Inline code in a return value floods
   the orchestrator's context and is discarded.
6. **Validate divergence before spending on collision** — digests' topology axes plus
   on-disk diffs (see the `topological-divergence` skill); honor `respawn-pair`
   exactly once, then proceed flagged or abort.

## Topology axes

| Axis | The fork it forces |
|---|---|
| data-model | change the state shape |
| control-flow | sync vs async; push vs pull; event vs polling |
| boundary | where the layer split sits |
| storage | in-memory vs queue vs DB; durable vs ephemeral |
| concurrency | single-writer vs lock vs CRDT |

Language packs (in `pqa-generator`) map these to stack-specific forks: Python
sync/async, dataclass/protocol, batch/stream; Rust ownership-by-move/Rc,
enum-state/trait-object; Go channels/mutex; SQL normalized/denormalized;
C/C++ arena/RAII, lock-free/locked. The axis must be structural for the stack at hand.

## Worked example

Task: "add rate limiting to the ingest API."

- b0 (data-model axis): fixed-window counter keyed per tenant — state is a counter.
- b1 (control-flow axis): bounded queue with backpressure; rejection propagates to the
  producer — state is queue depth, control flow is pull-based.
- b2 (P-reframe, scout): refuses "limit requests" entirely; surfaces a typed
  `Overloaded` error and makes the *caller* shed load — no limiter at all.

b1's digest, returned whole: `{"branch_id": "b1", "topology_axis": "pull-based
backpressure queue", "approach": "Bounded queue between ingest and workers; producer
receives queue-full and decides what to drop.", "files_touched": ["ingest/queue.py"],
"loc": 140, "conviction": "medium", "basis": "burst absorption beats rejection for
this producer mix"}`

Three different state shapes, three different failure modes — collision now has
something real to attack. Three restyled token buckets would have been noise billed
at fable prices.

## Anti-patterns

- **Hedging to the safe middle.** A generator that covers its own axis *and* its
  siblings' produces the average; the whole superposition fails when every branch
  averages.
- **Style-as-divergence.** Renamed variables, reordered functions, same AST shape —
  the divergence gate measures structure and will catch it.
- **Sibling awareness.** Passing branch A's digest into branch B's prompt to "avoid
  overlap" is convergence by contamination; the axes are the dedup mechanism.
- **Inline payloads.** Returning code instead of writing `.pqa/branches/bN/` breaks
  the ≤200-token-per-branch orchestrator contract and re-pays the payload in every
  downstream dispatch.
- **Branch-authored tests.** Generators never add to the test suite; the verifier runs
  the locked set. (`notes.md` may *propose* cases for humans; never add them.)
