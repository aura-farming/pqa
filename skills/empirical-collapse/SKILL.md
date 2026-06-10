---
name: empirical-collapse
description: Use when selecting the surviving branch on verifier evidence after collision.
---

# Empirical Collapse

Collapse converges the superposition onto one survivor using evidence only. The rule
is deliberately boring: verification gates, findings rank, conviction never enters.
The engine (`pqa.collapse.select_survivor`) is canonical; the judge mirrors it and
surfaces the reasoning — when they disagree, the engine wins and the disagreement goes
in the report.

## The collapse rule

1. Filter out branches with a critical unresolved adversary finding (deadly hits).
2. If any remaining branch has tests:
   - keep only those that passed verification;
   - none passed → **no survivor**: all branches failed; surface every death;
   - otherwise rank by `(findings_resolved desc, coverage desc, non-incremental first)`.
3. If no branch had tests at all: collapse on adversary findings only and flag the
   result **UNVERIFIED** — recommend tests.

The final tie-break toward the less incremental branch is the quantum jump: when the
evidence is equal, take the bigger defensible swing.

## Protocol

1. **Feed the judge structure only.** `pqa-collapse-judge` (model `fable`) receives
   the N digests, the findings JSON, and the verifier results — never raw code.
   P-relativize is judgment over evidence, and the evidence here is structured;
   "let me read the code to get a feel" is the eloquence reflex in a lab coat.
2. **Hold survivors as both-possibly-correct** until the rule selects. Two verified
   branches that both resolved their findings are BOTH live candidates; apply the
   ranking tuple, not a preference.
3. **Corroborate with the engine.** Build a
   `BranchResult(name, verified, has_tests, coverage, findings_resolved,
   findings_total, conviction, incremental)` per branch and run `select_survivor`.
   The invariant gate (`scripts/check_invariant.py`) statically forbids conviction
   from entering `_rank_key` — that is the one rule that cannot break, enforced in CI.
4. **Qualify confidence on every outcome:** `verified (94% coverage)` /
   `passes-but-thinly-tested (40% coverage)` / `verified (coverage unmeasured)` /
   `UNVERIFIED — no test suite`. Coverage is a confidence qualifier, never a victory
   lap.
5. **All-fail is a valid result.** Report each branch's specific death; never promote
   a least-bad branch silently. The dead branches feed the failure taxonomy — that is
   this run paying for the next one.

## Worked example

```python
from pqa.collapse import BranchResult, select_survivor
results = [
    BranchResult("b0", verified=True,  has_tests=True, coverage=91.0,
                 findings_resolved=1, findings_total=2, conviction=None,
                 incremental=True),
    BranchResult("b1", verified=True,  has_tests=True, coverage=84.0,
                 findings_resolved=3, findings_total=3, conviction="high",
                 incremental=False),
    BranchResult("b2", verified=False, has_tests=True, coverage=None,
                 findings_resolved=2, findings_total=4, conviction=None,
                 incremental=False),
]
outcome = select_survivor(results)
# b2 is out (failed verification). b1 beats b0 on findings_resolved (3 > 1) —
# coverage is never consulted, and conviction was never consulted at all.
# outcome.survivor.name == "b1"; outcome.confidence == "verified (84% coverage)"
```

Had b0 also resolved 3 findings, the tie would fall to coverage and b0's 91% would
beat b1's 84% — the non-incremental bit breaks only full ties, last. Walk the tuple
in order; never improvise the ranking.

## Anti-patterns

- **Eloquence tipping the scale.** The better-written rationale is not evidence.
- **Conviction tipping the scale.** Conviction shapes exploration; at collapse it is
  telemetry. A high-conviction loser still loses — and that row is the valuable part.
- **Premature collapse.** Picking "the obvious winner" before verifier results land
  is the collapse reflex the loop exists to suppress.
- **Least-bad merging.** An all-fail reported as a soft win poisons the registry and
  the operator's trust in the same move.
- **Judge overriding engine.** The judge explains; the engine decides. A silent
  override voids the auditability that justifies having a rule at all.
- **Re-ranking after the fact.** The survivor is the survivor; "but I prefer b0"
  belongs in a human review, not in the collapse record.
