---
name: git-worktree-orchestration
description: Use when isolating branches in git worktrees and reconciling the survivor.
---

# Git Worktree Orchestration

Worktree mode gives every superposition branch a real, isolated checkout: parallel
verifiers cannot race each other, branch payloads never touch the operator's working
tree, and a failed run can always be cleaned to zero orphans. The discipline is
lifecycle: spawn with cleanup armed, verify inside the tree, reconcile with
abort-on-conflict, prune always.

## Modes and namespace

- `branches_mode = "context" | "worktree"` (`pqa-config.toml` / `PQA_BRANCHES_MODE`).
  Context mode (the default) keeps branch payloads under `.pqa/branches/bN/`;
  worktree mode puts each branch on an ephemeral git branch `pqa/<run>-bN` checked
  out at `.pqa_worktrees/<run>-bN`.
- **Machine-managed namespace:** `pqa/*` branches and `.pqa_worktrees/` are PQA's to
  create and destroy. NOTHING else is. A cleanup step that touches a branch outside
  `pqa/<run>-*` is a defect, full stop.
- Status: the shell scripts below are the current interface; the engine-owned
  lifecycle (`pqa/worktrees.py` with a registry in `.pqa/state.json`) is roadmap §9.

## Protocol

1. **Spawn:** `scripts/spawn_branches.sh <run-id> <n>` — one worktree + branch per
   superposition branch off HEAD, echoing tree paths. Its EXIT trap removes every
   tree and branch it already created if ANY creation fails: a partial spawn must not
   orphan trees. If you reimplement spawning, keep that property — track created
   trees/branches as you go, clean on failure, `git worktree prune`.
2. **Generate into the tree.** Generators receive the worktree path and write real
   code there; commits on `pqa/<run>-bN` are the payload. Digests still come back
   ≤150 tokens — the worktree path replaces `.pqa/branches/bN/` in the loop contract.
3. **Verify INSIDE the worktree.** Run the real suite from within the branch's tree.
   This is the isolation context mode cannot give: two test runs in one tree race
   over caches, build artifacts, and bytecode files.
4. **Reconcile:** `scripts/reconcile.sh <run-id> [survivor-branch]`:
   - merges the survivor `--no-ff` so history shows the superposition happened;
   - a conflicted merge is **aborted** (`git merge --abort`), the survivor branch is
     preserved for a manual merge, and the script exits non-zero — the repo is never
     left mid-merge;
   - ALWAYS prunes: every `pqa/<run>-b*` tree and branch is removed (except an
     unmerged survivor), then `git worktree prune`. Cleanup runs whether or not the
     merge succeeded — losers die even when collapse failed.
5. **Assert clean state after every run:** `git worktree list` shows only real trees
   and `git branch --list 'pqa/*'` is empty (or exactly the preserved survivor).
   Zero orphans under failure injection is the acceptance bar.

## Worked example

```bash
scripts/spawn_branches.sh run42 3   # .pqa_worktrees/run42-b{1,2,3} on pqa/run42-b{1,2,3}
# generators commit into each tree; verifiers run the suite per-tree, in parallel
scripts/reconcile.sh run42 pqa/run42-b2   # b2 won
# -> merge --no-ff pqa/run42-b2; b1/b3 trees+branches removed; prune; "reconciled run run42"
```

Mid-run kill drill (the failure-injection test): kill the orchestrator between spawn
and reconcile, then run `scripts/reconcile.sh run42` with no survivor argument — the
cleanup pass removes all three trees and branches and exits 0. Idempotent: running it
again is a no-op.

Conflict drill: the survivor touches a file the main tree changed since spawn —
reconcile prints `merge conflict: aborted. Survivor branch 'pqa/run42-b2' preserved.`,
exits 1, `git status` shows a clean tree, and the operator merges by hand. The
reconciler never hand-resolves.

## Anti-patterns

- **Hand-resolving conflicts in the harness.** A conflict is an abort and a report;
  resolution is the operator's judgment, not the reconciler's.
- **Sharing one tree across parallel verifiers.** "It's usually fine" until two runs
  interleave artifacts — that race is the reason worktree mode exists.
- **Cleanup that trusts success.** Deleting trees only on the happy path is how
  orphans accumulate; the prune must run on failure too.
- **Touching non-machine-managed refs.** Any `git branch -D` outside `pqa/<run>-*` is
  data loss waiting for a glob bug.
- **Skipping `git worktree prune`.** Removing trees without pruning leaves stale
  administrative entries that block future spawns under the same name.
