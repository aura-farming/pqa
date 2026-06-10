---
description: Run the locked benchmark set, PQA versus baseline, honest results.
---

The falsifiability loop: does PQA actually beat a single pass?

Dispatch `pqa-eval-runner` via Task. It runs every task in `evals/tasks/` through both
arms (full loop vs `pqa-baseline-runner`) and scores each through
`scripts/eval_harness.py score` — the task's LOCKED verifier in a subprocess — then
aggregates with `scripts/eval_harness.py report <date>` into
`evals/results/<date>.json`.

Report the aggregate — wins, losses, ties, UNVERIFIED rate, cost ratio — losses
first. Never improvise tasks: the set in `evals/tasks/` with its locked verifiers IS
the benchmark.
