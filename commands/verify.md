---
description: Run the verifier standalone — real tests, types, lint, honest report.
argument-hint: [path]
---

Verification, standalone — the only signal from outside the model's distribution.

Dispatch `pqa-verifier` via Task on `$ARGUMENTS` (default: the working tree). It runs
the project's real test/type/lint commands and returns the structured result with a
confidence qualifier (`verified (N% coverage)` / `passes-but-thinly-tested` /
`UNVERIFIED — no test suite`).

Report the result verbatim, including the first failure detail when red. Never soften
a red into a "mostly passing".
