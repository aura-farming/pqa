"""Superposition via git worktrees. (Phase 2 — scaffold.)

Each branch gets an isolated worktree under .pqa_worktrees/ on an ephemeral pqa/* branch,
so generators work in true parallel without colliding on the working tree. reconcile.sh
merges the survivor and prunes the rest.
"""
from __future__ import annotations
