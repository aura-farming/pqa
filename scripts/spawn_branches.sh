#!/usr/bin/env bash
# Thin caller of the engine-owned lifecycle (pqa/worktrees.py): one git worktree per
# superposition branch on an ephemeral pqa/* branch, write-ahead registered in
# .pqa/state.json so strays survive even a mid-run SIGKILL (the old in-script trap
# could not). Rollback-on-partial-failure lives in the engine now.
# Usage: scripts/spawn_branches.sh <run-id> <n>      (run from the target repo root)
set -euo pipefail
RUN_ID="${1:?run id required}"
N="${2:-3}"
PQA_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="${PQA_SRC}${PYTHONPATH:+:${PYTHONPATH}}" exec python3 - "$RUN_ID" "$N" <<'PY'
import sys

from pqa.worktrees import spawn

for tree in spawn(sys.argv[1], int(sys.argv[2])):
    print(tree.path)
PY
