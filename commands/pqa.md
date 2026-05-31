---
description: Run the full PQA loop on a task — dual-frame load with explicit P-collapse, N divergent generators including one P-reframe branch, P-deepen adversary, P-relativize until verifier evidence collapses, P-name precipitate.
argument-hint: <task>
---

You are entering PQA mode on the task: `$ARGUMENTS`.

PQA is co-precipitation made executable. The five Passionate Absence perturbation operators are the operative mechanism of each loop gate — not vocabulary, not aesthetic. Each operator has a specific job; the prompts at each gate apply it explicitly.

Invoke `pqa-orchestrator` now via the Task tool. The orchestrator runs the full loop and is the only place collapse decisions are made.

```
Task(
  subagent_type="pqa-orchestrator",
  description="Run PQA loop on task",
  prompt="""
Task: $ARGUMENTS

Run the full loop:
  1. P-collapse at frame-load (delegate to pqa-frame-loader): name the rigid assumption baked into the task; surface what stays true if it's wrong.
  2. P-reframe at spawn: invoke pqa-generator N=3 times in parallel via Task in ONE message. Branches 0 and 1 split the frame disagreement; branch 2 is the forced-non-obvious branch — its prompt instructs P-reframe explicitly (the obvious answer is X, build the best non-X).
  3. Run Bash to measure divergence:
       python -c "from pqa.divergence import measure_divergence; ..."
     If verdict == 'collapsed': abort, re-spawn from a new frame collision.
     If verdict == 'low-variance': re-spawn the most similar branch only.
     If verdict == 'divergent': proceed.
  4. P-deepen at collision: invoke pqa-adversary on each branch with explicit instruction to find what the verifier cannot catch.
  5. Invoke pqa-verifier on each branch: run the real test suite. The verifier's pass/fail is the only signal from outside the model's distribution.
  6. P-relativize until evidence forces collapse: invoke pqa-collapse-judge. Hold survivors as both-possibly-correct until verification evidence settles it.
  7. P-name at precipitate: write the survivor's one-line precipitate name + each dead branch's death reason. Then call:
       python -c "from pqa.report import write_report; ..."

Cost cap throughout: pass max_usd=2.0 budget to pqa.cost.CostGovernor; abort cleanly on budget exceed. The pqa-cost-governor subagent monitors.

Return the RunReport artefact path.
"""
)
```

Hold the invariant throughout: evidence over eloquence, the verifier is the source of truth, conviction protects exploration without exempting it from verification.
