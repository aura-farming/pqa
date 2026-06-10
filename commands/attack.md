---
description: Run the adversary standalone against current code or a path.
argument-hint: [path]
---

Adversarial collision, standalone — no full loop, one attack pass.

Dispatch `pqa-adversary` via Task on the target (default: the working tree's recent
changes; otherwise the path in `$ARGUMENTS`). It reads the code itself and returns
findings JSON: what the verifier cannot catch — silent assumptions, unexercised
boundaries, security posture, unjustified complexity.

Present the findings grouped by severity, critical first, each with its concrete
trigger. Do not fix anything; that is the operator's call.
