---
name: topological-divergence
description: Use when measuring whether branches genuinely differ and deciding respawn or abort.
---

# Topological Divergence

"Branches must differ in topology, not style" is an assertion until something measures
it. This gate measures it: superposition can silently collapse into N near-identical
branches and waste the whole run's spend. The metric is AST shape, so a renamed
variable does NOT count as divergence but a changed control flow does.

## How the metric works

- `pqa.divergence.similarity(a, b)` fingerprints each branch as its pre-order AST
  node-type sequence (`depth:NodeType` lines) and ratios the fingerprints with
  `difflib.SequenceMatcher`. 1.0 = identical topology; renames and reformatting do
  not move the score.
- Non-parseable (non-Python) text falls back to whitespace-stripped comparison —
  weaker signal, still useful.
- `measure_divergence(branches, collapsed_at=0.95, divergent_below=0.7)` scores every
  pair and returns a `DivergenceReport` with a verdict:

| Verdict | Condition | Orchestrator action |
|---|---|---|
| divergent | mean < 0.7 and max < 0.95 | proceed to collision |
| low-variance | one pair ≥ 0.95, or mean in [0.7, 0.95) | respawn-pair: redo the most similar branch |
| collapsed | mean ≥ 0.95 (or n < 2) | abort; re-spawn the whole superposition |

A superposition of 0 or 1 branches is "collapsed" by definition — degenerate runs do
not sneak past the gate.

## Protocol

1. **Check digests first, diffs second.** The `topology_axis` fields on the returned
   digests are the cheap signal: two branches claiming the same axis is a respawn
   candidate before any AST work. Then confirm on the on-disk outputs via
   `pqa.superposition.validate_divergence(branches)`.
2. **Translate the report with `respawn_plan(report)`** — it returns `proceed`,
   `respawn-pair` (with `pair_indices` naming the most similar pair), or `abort`.
3. **Honor respawn-pair exactly once.** Re-spawn ONLY the more derivative branch of
   the flagged pair, with a stronger P-reframe directive; the other branch stands.
   One respawn, then proceed flagged or abort — a respawn loop is budget death by
   optimism.
4. **On abort, record it.** A collapsed superposition is a failure-taxonomy row with
   the `divergence:` prefix: the prompts produced convergence, so the next run needs
   sharper axes — it is a prompt failure, never evidence against the approach itself.
5. **Journal the gate.** The divergence verdict and any respawn belong in the
   `superpose` stage record in `.pqa/state.json`, so `--resume` re-enters after the
   gate rather than re-paying the generators.

## Worked example

Two rate-limiter branches come back:

```python
# b0                                   # b1
def allow(key):                        def permit(tenant):
    n = counts[key]                        c = window[tenant]
    if n >= LIMIT:                         if c >= MAX:
        return False                           return False
    counts[key] = n + 1                    window[tenant] = c + 1
    return True                            return True
```

Different names, same shape: both fingerprint to the same
`Module/FunctionDef/Assign/If/Compare/Return/...` sequence → similarity ≈ 1.0 → the
pair is flagged, verdict `low-variance`, `respawn_plan` returns respawn-pair on
(0, 1). The respawned b1 comes back as a bounded queue with backpressure — `While`,
`Try`, `Raise` nodes the fingerprint cannot mistake for a counter — similarity drops
to ~0.3, verdict `divergent`, proceed.

The gate caught what eyeballing the diff at 2am would have missed: the superposition
was one idea wearing two names, about to be billed twice at fable prices.

## Anti-patterns

- **Style-as-divergence.** Different formatting, naming, or comment density over the
  same AST shape is ONE branch billed N times.
- **Respawning more than once.** The plan grants exactly one respawn-pair attempt;
  past that, proceed flagged or abort — never chase divergence with the budget.
- **Ignoring `collapsed`.** Attacking three identical branches gives the adversary
  nothing to compare and the judge nothing to choose; aborting is cheaper than
  theatre.
- **Fixing the seed, keeping the axis.** If `spawn_prompts` axes were vague, a respawn
  with the same axis converges again — sharpen the axis, not just the retry.
- **Over-trusting the text fallback.** For non-Python branches similarity is textual;
  weigh `low-variance` verdicts with more skepticism there, not less.
