---
name: cost-aware-pipeline
description: Use when budgeting, routing, and scaling a run to fit the ask.
---

# Cost-Aware Pipeline

A harness that cannot finish under its own cost gates — or that burns a build-sized
budget answering a question — is anti-enhancement. The economics rest on four levers:
tokens as the primary ledger, the scale gate, model routing by job, and killing
branches before the expensive passes see them.

## Tokens first, USD second

PQA runs on a Claude Code subscription: USD is synthetic; tokens, rate limits, and
context are real. `Budget(max_usd, max_tokens, warn_at=0.8)` trips on EITHER axis;
`run_budget_tokens` (default 800k) is the number that matters and `run_budget_usd`
(default 5.0) is the display/API-mode cap. Model identity flows through ONE
translation point — `pqa.cost.resolve_model` (aliases `fable|opus|sonnet|haiku`) — so
projection, dispatch, and recording can never price different models for the same call.

## The scale gate (before anything is spent)

| Ask | Mode | Spend shape |
|---|---|---|
| compare / choose / review / explain | decide | frames + ONE judge pass over idea digests; < 30k tokens; output flagged `judgment — not verifier-backed` |
| single-file fix, rename, config tweak | patch | n_branches=2, no scout, abbreviated frame |
| feature / refactor with real unknowns | build | full loop, N from config |

Never silently upgrade a decide-ask into a build run — a question answered with a full
superposition is the harness's worst failure mode: enormous spend for an answer one
judgment pass could give. When unsure, ask the operator which mode they want.

## Model routing (the biggest lever)

| Tier | Work | Agents |
|---|---|---|
| fable | coding + quality-critical judgment | generator (every branch), unknown-scout, adversary, collapse-judge, baseline-runner (fair control) |
| sonnet | mechanical execution + orchestration | orchestrator, frame-loader, verifier, reconciler, self-reflector, instinct-synthesizer |
| haiku | bookkeeping | memory-curator, failure-taxonomist, eval-runner |

Pass `model` explicitly on every Task dispatch. Never burn fable tokens on arithmetic,
table rendering, or registry writes. The table is enforced by
`scripts/validate_components.py` — adding an agent means making a routing decision.

## Two gates around every dispatch

1. **Pre-flight:** `governor.would_abort(model, projected_in, projected_out)` — if
   True, do NOT dispatch: write the aborted RunReport (partial state,
   `memories_injected` included) and stop. Projections are pessimistic by design
   (`max(len(prompt)//3, floor)` input, fixed output floor): refuse a dispatch that
   might fit rather than admit one that won't.
2. **Post-call:** `governor.record(branch_id, model, actual_in, actual_out)` from the
   subagent's reported usage, then `should_abort()` as belt-and-braces.
   `should_abort()` alone fires after the money is spent — that asymmetry is why both
   gates exist.

## Spend on survivors, not corpses

Order verification by cost: lint/type-check (seconds, zero tokens) kills
compile-broken branches BEFORE the adversary, so the most expensive judgment pass only
attacks branches that could win. The same shape applies everywhere: cheap gates first,
fable last.

## Worked example

N=3 build run, 800k-token budget: frame (sonnet, ~25k) → 3 generators (fable, ~3×90k)
→ static early-kill (0 tokens — b1 dies on pyright; taxonomy row `verifier: failed
static checks before collision — pyright: 4 errors`) → 2 adversaries (fable, ~2×60k)
→ 2 verifiers (sonnet, ~2×30k) → judge (fable, ~20k) → bookkeeping (haiku, ~10k)
≈ 410k total: completes with headroom.

The same run WITHOUT early-kill pays ~60k fable tokens attacking a branch that could
never merge. The same ask phrased as "which approach is better?" should have cost
< 30k in decide mode — two orders of magnitude apart, governed by the gate, not luck.

A run that does abort mid-loop records every live branch as `budget: aborted at
collide, 612k/800k tokens spent` — and retrieval never reads those rows as refuted
(see failure-taxonomy).

## Anti-patterns

- **USD-primary thinking.** Optimizing cents while blowing the context window or rate
  limit optimizes the wrong scarcity.
- **Post-hoc-only gating.** `should_abort()` without `would_abort()` bills you for the
  dispatch that broke the budget.
- **Routing everything to fable.** Bookkeeping on the top model is pure waste — and
  the validator rejects the frontmatter anyway.
- **Adversary before static checks.** Paying judgment prices to discover a syntax
  error.
- **Optimistic projections.** Projections exist to refuse; an optimistic floor turns
  the pre-flight gate into decoration.
- **`/cost` or `/budget` dispatching a model.** They are Bash wrappers over the
  engine's ledger — a model call to read a number is the disease in miniature.
