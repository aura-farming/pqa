---
description: Render the PQA memory dashboard — precipitates, the failure-taxonomy moat, and conviction-vs-reality — from the local memory DB.
---

Run the PQA dashboard:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/dashboard.py" "${PQA_MEMORY_DB:-.claude/hooks/memory/pqa_memory.db}"
```

Summarise what the accumulated memory shows: which precipitates keep winning, which approaches
keep dying (the moat), and where conviction diverged from the verifier. Hold the PQA invariant.
