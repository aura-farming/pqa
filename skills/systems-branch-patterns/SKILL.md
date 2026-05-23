---
name: systems-branch-patterns
description: Divergence in C/C++/systems (arena/RAII, lock-free/locked, SoA/AoS). Use when: Systems superposition.
---

# Systems Branch Patterns

## Purpose
Divergence in C/C++/systems (arena/RAII, lock-free/locked, SoA/AoS).

## When to use
Systems superposition.

## How it fits PQA
Pairs with pqa-systems-brancher.
It serves the loop (frame -> superpose -> collide -> collapse -> precipitate) and the governing principle: spread probability mass into divergent
and low-probability branches, then collapse it onto whatever survives attack and verification.

## Discipline
Evidence over eloquence. Name what precipitates. Report confidence honestly. Never let a
persuasive rationale substitute for a passing test.
