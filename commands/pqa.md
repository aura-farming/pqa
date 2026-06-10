---
description: Run the PQA loop scaled to the task; --resume re-enters a crashed run.
argument-hint: <task> | --resume <session_id> | --step <stage>
---

You are entering PQA mode on: `$ARGUMENTS`.

PQA is co-precipitation made executable: hold divergent solutions in tension, attack
them, and converge only on what survives attack **and** tests. The loop and its gate
mechanics live in ONE place — the `pqa-orchestrator` agent. Do not restate or
improvise the loop here.

The orchestrator's **scale gate** sizes the run to the ask: compare/choose/review
questions get a frames-plus-judge pass (no branch generation, no mass token spend);
small patches get 2 branches; only substantive build/refactor work gets the full loop.
`--step <stage>` runs a single gate (frame, superpose, collide, verify, collapse,
precipitate) for debugging.

Invoke it now:

```
Task(
  subagent_type="pqa-orchestrator",
  description="Run PQA loop",
  prompt="""
Task: $ARGUMENTS
Session: derive a filesystem-safe session_id (e.g. pqa-<unix-epoch>); if the
arguments contain `--resume <session_id>`, use that id and re-enter at the first
incomplete stage per .pqa/state.json.

Run the loop end-to-end per your own instructions. Return the report artifact path,
the one-line precipitate name, and the confidence qualifiers (coverage, unresolved
findings).
"""
)
```

Hold the invariant: evidence over eloquence — the verifier is the source of truth,
and conviction protects exploration without exempting it from verification.
