---
description: Run the full PQA loop on a task; --resume re-enters a crashed run at its first incomplete stage.
argument-hint: <task> | --resume <session_id>
---

You are entering PQA mode on: `$ARGUMENTS`.

PQA is co-precipitation made executable: hold divergent solutions in tension, attack
them, and converge only on what survives attack **and** tests. The loop and its gate
mechanics live in ONE place — the `pqa-orchestrator` agent. Do not restate or
improvise the loop here.

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
