#!/usr/bin/env bash
# Thin caller of pqa.worktrees.reconcile: merge the survivor (--no-ff), then prune
# ALL ephemeral worktrees+branches for the run. Cleanup always happens, even when
# the merge conflicts — the survivor branch is preserved for a manual merge and the
# script exits 1. Idempotent; strays are found via the .pqa/state.json registry,
# the worktree directory, and git's branch list.
# Usage: scripts/reconcile.sh <run-id> [survivor-branch-or-empty]
set -euo pipefail
RUN_ID="${1:?run id required}"
SURVIVOR="${2:-}"
PQA_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="${PQA_SRC}${PYTHONPATH:+:${PYTHONPATH}}" exec python3 - "$RUN_ID" "$SURVIVOR" <<'PY'
import sys

from pqa.worktrees import reconcile

result = reconcile(sys.argv[1], sys.argv[2] or None)
if result.merge_failed:
    print(
        f"merge conflict or failure: survivor branch '{result.preserved_branch}' kept.\n"
        f"reconcile incomplete for run {result.run_id}: "
        f"merge {result.preserved_branch} manually",
        file=sys.stderr,
    )
    sys.exit(1)
print(f"reconciled run {result.run_id}")
PY
