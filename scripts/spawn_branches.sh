#!/usr/bin/env bash
# Spawn one git worktree per superposition branch on an ephemeral pqa/* branch.
# Usage: scripts/spawn_branches.sh <run-id> <n>
set -euo pipefail
RUN_ID="${1:?run id required}"
N="${2:-3}"
ROOT=".pqa_worktrees"
mkdir -p "$ROOT"
for i in $(seq 1 "$N"); do
  BRANCH="pqa/${RUN_ID}-b${i}"
  TREE="${ROOT}/${RUN_ID}-b${i}"
  git worktree add -b "$BRANCH" "$TREE" HEAD >/dev/null
  echo "$TREE"
done
