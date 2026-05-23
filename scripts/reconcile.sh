#!/usr/bin/env bash
# Merge the surviving branch, then prune ALL ephemeral worktrees+branches for the run.
# Idempotent and safe to run even when collapse failed (cleanup must always happen).
# Usage: scripts/reconcile.sh <run-id> [survivor-branch-or-empty]
set -euo pipefail
RUN_ID="${1:?run id required}"
SURVIVOR="${2:-}"
ROOT=".pqa_worktrees"

if [[ -n "$SURVIVOR" ]]; then
  git merge --no-ff "$SURVIVOR" -m "feat: merge PQA survivor ${SURVIVOR}" || \
    echo "merge needs manual resolution: $SURVIVOR"
fi

# Always clean up, survivor or not.
for TREE in "${ROOT}/${RUN_ID}-b"*; do
  [[ -d "$TREE" ]] || continue
  git worktree remove --force "$TREE" 2>/dev/null || true
done
for BRANCH in $(git branch --list "pqa/${RUN_ID}-b*" | tr -d ' *'); do
  git branch -D "$BRANCH" 2>/dev/null || true
done
git worktree prune
echo "reconciled run ${RUN_ID}"
