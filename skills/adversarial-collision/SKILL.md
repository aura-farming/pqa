---
name: adversarial-collision
description: Use when attacking branches to find what the verifier cannot catch.
---

# Adversarial Collision

The collide step applies P-deepen to every live branch: refuse the surface answer and
find what tests, types, and lint cannot see. The adversary breaks; it never fixes —
fixing your own findings is self-grading, the test-gaming failure mode.

## When to use

- After superposition digests return and static early-kill has run, before
  verification results are ranked.
- NOT in `decide` mode — there is no adversary pass on a question; the judge weighs
  idea digests directly.

## Protocol

1. **Early-kill first, attack second.** Run the project's lint/type/compile per branch
   (e.g. `uv run ruff check . && uv run pyright`) BEFORE dispatching any model. A
   branch that fails static checks is recorded to the failure taxonomy
   (`death_reason: "failed static checks before collision"`) and excluded. The
   adversary is the most expensive judgment pass; it only attacks branches that could
   possibly win.
2. **Dispatch per branch, in parallel, by path.** ONE message, one `fable` Task per
   live branch, each given `.pqa/branches/bN/` (or its worktree) — the adversary Reads
   the code and `notes.md` in its own context. Never inline branch code into dispatch
   prompts.
3. **Attack the eight layers the verifier cannot reach:**
   - solved the actual question vs a shallow restatement of it
   - input-distribution assumptions vs reality
   - behaviour at the boundaries no test exercises
   - security posture under adversarial input
   - complexity vs what it actually buys
   - failure-mode recoverability (vs silent data loss)
   - the promised contract vs what callers actually need
   - resource scaling (memory, time, lock contention)
4. **Findings as structured JSON only:** `{branch_id, severity, category, title,
   detail, resolved: false}` — `detail` names the trigger input/condition and why the
   verifier misses it. `resolved` is always `false` from the adversary.
5. **Attack conviction-flagged branches harder.** `conviction: high` protects a branch
   from early pruning — it buys attention, not leniency. "High-conviction branch
   failed under attack" is the best calibration row the system records.
6. **Attack the branch's tests too.** Would they pass on `return None`? Do they assert
   values or just shapes? Tests that would survive mutation are a critical finding —
   they compromise the verifier signal itself.
7. **One defense pass, then score.** Each attacked branch may answer its own findings
   (own context, reading its own findings JSON); then `pqa.collision.score_all`. A
   critical unresolved finding is a deadly hit.
8. **Cross-branch comparison runs over findings JSON**, never over code — one cheap
   second pass, only when genuinely needed.

## Severity honesty

| Severity | Meaning | Effect at collapse |
|---|---|---|
| critical | fails its purpose in a way the verifier misses (corruption, bypass, deadlock, silently wrong output) | unresolved = branch dies regardless of tests |
| high | real bug a competent reviewer blocks on | weighs against; not fatal |
| medium | suboptimal in a way that matters | tie-break material |
| low | style, naming | surface it; spend no budget |

Critical inflation destroys the gate: if everything is critical, the orchestrator
learns to discount the adversary, and the one finding that matters drowns.

## Worked example

Branch b0, fixed-window rate limiter. Verifier: green, 91% coverage. The finding:

```json
{"branch_id": "b0", "severity": "critical", "category": "correctness",
 "title": "burst-at-boundary admits 2x the limit",
 "detail": "Two windows sharing an edge each admit a full quota: 100 requests at
 09:59:59.9 plus 100 at 10:00:00.1 — 200 admitted in 200ms against a 100/min limit.
 No test exercises a window edge, so the verifier stays green.",
 "resolved": false}
```

b0's defense pass cannot resolve it without changing topology (sliding window), so the
finding stands and b0 dies despite passing verification. That is the gate working:
green tests are necessary, never sufficient.

## Anti-patterns

- **Politeness.** Branches don't have feelings; soft findings are wasted fable tokens.
- **Speculative theatre.** A finding without a concrete trigger — specific input,
  condition, call sequence — is vibes, and the judge must discount it.
- **Fixing.** The adversary proposing patches collapses the attack/defense separation
  the loop depends on.
- **Skipping the "obviously fine" branch.** The verifier already certified looks-fine;
  the adversary's entire jurisdiction starts past that point.
- **Severity theatre.** Attacking style at `low` in volume crowds out the one
  `critical` that decides the run.
