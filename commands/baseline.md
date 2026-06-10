---
description: Record the honest single-pass baseline for a task.
argument-hint: <task>
---

The control arm: one single-pass attempt, no loop, recorded for the side-by-side.

Dispatch `pqa-baseline-runner` via Task on: `$ARGUMENTS`. It solves the task in one
pass (same model the PQA generators use — a fair control), runs the test suite once,
writes its solution under `.pqa/baseline/`, and records the row via
`pqa.baseline.record_baseline`.

Report: pass/fail, coverage, tokens used, and where the solution was written.
