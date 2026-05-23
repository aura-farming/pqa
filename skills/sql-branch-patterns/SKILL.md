---
name: sql-branch-patterns
description: Divergence in data/query design (normalised/denormalised, window/subquery, index strategy). Use when: Data superposition.
---

# Sql Branch Patterns

## Purpose
Divergence in data/query design (normalised/denormalised, window/subquery, index strategy).

## When to use
Data superposition.

## How it fits PQA
Pairs with pqa-sql-brancher.
It serves the loop (frame -> superpose -> collide -> collapse -> precipitate) and the governing principle: spread probability mass into divergent
and low-probability branches, then collapse it onto whatever survives attack and verification.

## Discipline
Evidence over eloquence. Name what precipitates. Report confidence honestly. Never let a
persuasive rationale substitute for a passing test.
