---
description: Show recorded run costs from the engine; no model call.
---

Pure Bash wrapper — never dispatch an agent for arithmetic:

```bash
python3 <<'PY'
from pqa.config import load_or_defaults
from pqa.memory import connect
conn = connect(load_or_defaults().memory_db)
rows = conn.execute(
    "SELECT session_id, task, total_cost, budget_usd, status, branches,"
    " datetime(created_at,'unixepoch') FROM cost_runs"
    " ORDER BY created_at DESC LIMIT 10").fetchall()
print(f"{'session':<22}{'cost':>8}{'budget':>8}  {'status':<8}{'when':<20} task")
for s, t, c, b, st, n, w in rows:
    print(f"{s:<22}{c:>8.2f}{b:>8.2f}  {st:<8}{w:<20} {t or ''}")
PY
```

Show the table. No rows → "no recorded runs yet."
