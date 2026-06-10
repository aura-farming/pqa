---
name: failure-taxonomy
description: Use when recording dead branches so future runs avoid re-litigating them.
---

# Failure Taxonomy

Dead branches are the continuous-learning asset — but only if their deaths are
recorded precisely enough to retrieve later. The difference between "didn't work" and
a useful taxonomy row is the whole discipline: a future frame-loader matches on shape
and verbatim symptoms, not on summaries.

## The row

`pqa.memory.record_failure(conn, session, task, Failure(approach, death_reason, conviction))`

- **approach** — the topology, not the implementation: "fixed-window counter",
  "trait-object state machine", "denormalized read model". A future task matches on
  shape; "used a dict" matches nothing.
- **death_reason** — VERBATIM from the killer: the first failing assertion from the
  verifier, or the adversary finding's title + trigger condition. "fails
  burst-at-boundary when two windows share an edge" retrieves; "had some test issues"
  does not.
- **conviction** — the branch's flagged level (`high|medium|low|none`).
  High-conviction deaths are the calibration loop's best rows.

## Layer prefixes — who killed it

Prefix the death_reason with the killing layer when it is not obvious:

| Prefix | Meaning | Retrieval semantics |
|---|---|---|
| `verifier:` | failed real tests/types/lint | approach refuted in this context |
| `adversary:` | critical unresolved finding | approach has a named hole |
| `divergence:` | superposition collapsed; branch was a duplicate | prompt/axis failure, NOT approach failure |
| `budget:` | run aborted before judgment | **NOT a merit death** — never retrieve as refutation |
| `reconcile:` | passed in branch, failed after merge | approach interacts badly with the tree |

The `budget:` prefix is load-bearing: an aborted run must never teach the harness that
an approach is bad. The prefix is what protects it from being read as evidence.

## Protocol

1. **Search before write.** `search_failures(conn, task, limit=5)` (FTS5
   relevance-ranked, LIKE fallback on FTS5-less builds). A hit with the same substance
   — same approach, same death reason — means update the story, not duplicate the row:
   record the new occurrence referencing the prior id ("second death, see
   failure:12"). A taxonomy is not a log.
2. **Record every dead branch, including boring deaths.** Boring deaths repeat the
   most; the row costs tokens once and saves a branch every time it retrieves.
3. **Keep secrets out** of approach and death_reason — registries persist across runs
   and exports. The secrets hook guards reads; the writer is the last line.
4. **Retrieve by relevance at frame-load, never recency.** `prior_art(conn, task,
   max_tokens=400)` is the sanctioned injection: ranked, token-capped, ids cited so
   the run report can name what shaped the frame (`memories_injected`).
5. **Append-only.** Wrong rows are superseded by sharper rows, never deleted —
   supersession is itself signal that the first description missed something.

## Worked example

Bad row (useless tomorrow):

```
approach: "rate limiter v2"        death_reason: "tests failed"
```

Good row (retrieves and teaches):

```
approach:     "fixed-window per-tenant counter"
death_reason: "verifier: test_burst_at_boundary — 200 admitted in 200ms against
               100/min limit; windows sharing an edge each grant full quota"
conviction:   "none"
```

Next month, task "throttle webhook fan-out": `search_failures` matches the
window/limit shape, `prior_art` injects the row with its id, the frame-loader surfaces
`failure:12` in the self-eval frame, and the spawn prompts either exclude fixed-window
or demand the boundary case be handled. One recorded death = one branch not wasted, in
every future run that rhymes with this one.

Budget contrast: the same branch dying because the run hit its token cap is recorded
as `budget: aborted at collide stage, 612k/800k tokens spent` — and when retrieved it
reads as "untested", never as "refuted".

## Anti-patterns

- **Paraphrasing the killer.** Summaries feel cleaner and retrieve worse. Verbatim or
  nothing.
- **Implementation-naming.** "used asyncio" is not an approach; "single-writer event
  loop, no locks" is.
- **Skipping boring deaths.** The fifth duplicate death you didn't record is the sixth
  duplicate branch you will pay for.
- **Letting budget deaths refute.** An aborted run treated as evidence poisons every
  future frame that retrieves it.
- **Deleting rows.** Append-only; supersede with sharper rows.
