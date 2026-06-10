---
description: Install PQA hooks, agents, and memory at project or system scope.
argument-hint: <project|system>
---

```bash
bash scripts/install.sh "$ARGUMENTS"
```

The script wires hooks, seeds the memory DB via the migration runner, and creates
`.pqa/`. Report what it printed — including the scope it installed to — and surface
any non-zero exit verbatim. Default scope when `$ARGUMENTS` is empty: `project`.
