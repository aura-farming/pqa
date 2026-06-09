#!/usr/bin/env bash
# Spawn one git worktree per superposition branch on an ephemeral pqa/* branch.
# Usage: scripts/spawn_branches.sh <run-id> <n>
set -euo pipefail
RUN_ID="${1:?run id required}"
N="${2:-3}"
ROOT=".pqa_worktrees"

# On ANY failure, remove every worktree+branch this invocation already created —
# a partial spawn must not orphan trees. Bash-3.2-safe empty-array expansion.
CREATED_TREES=()
CREATED_BRANCHES=()
cleanup_on_failure() {
  local code=$?
  if [[ $code -ne 0 ]]; then
    echo "spawn failed (exit ${code}) — removing partial worktrees" >&2
    for t in ${CREATED_TREES[@]+"${CREATED_TREES[@]}"}; do
      git worktree remove --force "$t" 2>/dev/null || true
    done
    for b in ${CREATED_BRANCHES[@]+"${CREATED_BRANCHES[@]}"}; do
      git branch -D "$b" 2>/dev/null || true
    done
    git worktree prune 2>/dev/null || true
  fi
}
trap cleanup_on_failure EXIT

mkdir -p "$ROOT"
for i in $(seq 1 "$N"); do
  BRANCH="pqa/${RUN_ID}-b${i}"
  TREE="${ROOT}/${RUN_ID}-b${i}"
  git worktree add -b "$BRANCH" "$TREE" HEAD >/dev/null
  CREATED_TREES+=("$TREE")
  CREATED_BRANCHES+=("$BRANCH")
  echo "$TREE"
done
