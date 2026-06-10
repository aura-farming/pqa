# Configuration reference

> GENERATED from `pqa/config.py` by `scripts/generate_config_doc.py` — do not edit
> by hand. Regenerate with `uv run python scripts/generate_config_doc.py`;
> `tests/test_config_doc.py` pins this file against the code.

Settings come from the `[pqa]` table of `pqa-config.toml` and/or `PQA_*`
environment variables. Precedence: **env > TOML > defaults**, resolved in one
pass at load time. The loader is stdlib-only and strict: wrong-typed values,
unknown keys, non-finite budgets, and `memory_db` paths into system directories
are rejected with the offending origin named. See
[`pqa-config.example.toml`](../pqa-config.example.toml).

## Keys at a glance

| Key | Type | Default | Env var |
|-----|------|---------|---------|
| `branches` | int | `3` | `PQA_BRANCHES` |
| `verify_tests` | bool | `False` | `PQA_VERIFY_TESTS` |
| `model` | str | `'fable'` | `PQA_MODEL` |
| `run_budget_usd` | float | `5.0` | `PQA_RUN_BUDGET_USD` |
| `run_budget_tokens` | int | `800000` | `PQA_RUN_BUDGET_TOKENS` |
| `max_spiral_depth` | int | `1` | `PQA_MAX_SPIRAL_DEPTH` |
| `branches_mode` | str | `'context'` | `PQA_BRANCHES_MODE` |
| `memory_db` | str | `'.claude/hooks/memory/pqa_memory.db'` | `PQA_MEMORY_DB` |

## What each key does

### `branches`

How many divergent solutions one run holds in superposition. More branches buy more exploration and more spend; the divergence gate kills lookalikes either way. Must be >= 1.

### `verify_tests`

When true, the verify_loop hook runs the test suite after every edit on top of its default lint check — a per-session belt for high-stakes work. The binding merge-time guarantee stays in CI regardless.

### `model`

Operator model preference as a short alias; `PQAConfig.resolved_model()` translates it to the concrete dispatch/pricing id via `pqa.cost.resolve_model`. The orchestrator routes models per role — quality-critical roles run Fable 5; mechanical tiers run cheaper models.

Allowed values: `fable`, `haiku`, `opus`, `sonnet`.

### `run_budget_usd`

Secondary spend cap and display currency. The cost governor aborts the run cleanly (partial RunReport, spend snapshot) the moment a cap is crossed. Must be a finite number > 0.

### `run_budget_tokens`

PRIMARY spend ledger: tokens are counted before USD. Sized so a routed N=3 run completes with headroom. Must be >= 10000 — a full run cannot fit in less.

### `max_spiral_depth`

How many times a finished run may re-enter the loop on its own result (/spiral). 0 disables spirals; the cap exists because a budget is a brake, not a steering wheel. Must be in [0, 5].

### `branches_mode`

`context`: branches run in-context, sequentially (works anywhere, no git needed). `worktree`: one isolated git worktree per branch on an ephemeral `pqa/<run>-bN` branch (pqa.worktrees), with a write-ahead registry in `.pqa/state.json` for crash-safe cleanup and true verifier isolation.

Allowed values: `context`, `worktree`.

### `memory_db`

SQLite path for the continuous-learning store (precipitates, failures, signals, frames, instincts). Created on first use via the migration runner. Paths resolving into system directories are refused.
