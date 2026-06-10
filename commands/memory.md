---
description: Search the precipitate and failure registries; preview prior art.
argument-hint: <query>
---

Query the moat (read-only, no Task dispatch needed):

```bash
python3 <<'PY'
from pqa.config import load_or_defaults
from pqa.memory import connect, prior_art, search_failures, search_precipitates
conn = connect(load_or_defaults().memory_db)
q = """$ARGUMENTS"""
print("failures:", search_failures(conn, q))
print("precipitates:", search_precipitates(conn, q))
print("--- prior-art block (what frame-load would inject) ---")
print(prior_art(conn, q).text or "(nothing relevant)")
PY
```

Summarize the hits with their ids (`failure:N` / `precipitate:N`) so they can be
cited or audited. Empty results are an answer — report "no prior art", don't pad.
