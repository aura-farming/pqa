#!/usr/bin/env bash
# Merge the surviving branch, then prune ALL ephemeral worktrees+branches for the run.
# Idempotent and safe to run even when collapse failed (cleanup must always happen).
# Usage: scripts/reconcile.sh <run-id> [survivor-branch-or-empty]
set -euo pipefail
RUN_ID="${1:?run id required}"
SURVIVOR="${2:-}"
ROOT=".pqa_worktrees"

MERGE_FAILED=0
if [[ -n "$SURVIVOR" ]]; then
  if ! git merge --no-ff "$SURVIVOR" -m "feat: merge PQA survivor ${SURVIVOR}"; then
    # Never leave the repo mid-merge: abort, preserve the survivor branch for a
    # manual merge, and report failure via exit code.
    git merge --abort 2>/dev/null || true
    MERGE_FAILED=1
    echo "merge conflict: aborted. Survivor branch '${SURVIVOR}' preserved." >&2
  fi
fi

# Always clean up, survivor or not.
for TREE in "${ROOT}/${RUN_ID}-b"*; do
  [[ -d "$TREE" ]] || continue
  git worktree remove --force "$TREE" 2>/dev/null || true
done
for BRANCH in $(git branch --list "pqa/${RUN_ID}-b*" | tr -d ' *'); do
  if [[ "$MERGE_FAILED" -eq 1 && "$BRANCH" == "$SURVIVOR" ]]; then
    continue  # keep the unmerged survivor's commits reachable
  fi
  git branch -D "$BRANCH" 2>/dev/null || true
done
git worktree prune
if [[ "$MERGE_FAILED" -eq 1 ]]; then
  echo "reconcile incomplete for run ${RUN_ID}: merge ${SURVIVOR} manually" >&2
  exit 1
fi
echo "reconciled run ${RUN_ID}"
