---
description: Run the locked benchmark set, PQA versus baseline, honest results.
---

The falsifiability loop: does PQA actually beat a single pass?

Dispatch `pqa-eval-runner` via Task. It runs every task in `evals/` through both arms
(full loop vs `pqa-baseline-runner`), scores each with that task's locked verifier,
and appends to `evals/results/<date>.json`.

Report the aggregate — wins, losses, ties, UNVERIFIED rate, cost ratio — losses
first. If `evals/` is missing, say so and point at the roadmap's benchmark spec
instead of improvising tasks.
