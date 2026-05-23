---
name: git-worktree-orchestration
description: One isolated worktree per branch on an ephemeral pqa/* branch; clean reconcile that never orphans trees. Use when: Parallel superposition.
---

# Git Worktree Orchestration

## Purpose
One isolated worktree per branch on an ephemeral pqa/* branch; clean reconcile that never orphans trees.

## When to use
Parallel superposition.

## How it fits PQA
The mechanism that makes branches genuinely parallel and cheap to discard.
It serves the loop (frame -> superpose -> collide -> collapse -> precipitate) and the governing principle: spread probability mass into divergent
and low-probability branches, then collapse it onto whatever survives attack and verification.

## Discipline
Evidence over eloquence. Name what precipitates. Report confidence honestly. Never let a
persuasive rationale substitute for a passing test.
