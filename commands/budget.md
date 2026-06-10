---
description: Inspect the configured run budgets; no model call.
---

Pure Bash wrapper — budgets live in config, not in an agent's opinion:

```bash
python3 <<'PY'
from pqa.config import load_or_defaults
cfg = load_or_defaults()
print(f"run_budget_tokens : {cfg.run_budget_tokens:,}   (primary ledger)")
print(f"run_budget_usd    : ${cfg.run_budget_usd}      (secondary/display)")
print(f"branches          : {cfg.branches}")
print(f"max_spiral_depth  : {cfg.max_spiral_depth}")
print(f"model             : {cfg.model} -> {cfg.resolved_model()}")
PY
```

To change a budget, point the operator at `pqa-config.toml` or the env overrides
(`PQA_RUN_BUDGET_TOKENS`, `PQA_RUN_BUDGET_USD`) — do not edit config files for them.
