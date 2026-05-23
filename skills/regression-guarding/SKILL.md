---
name: regression-guarding
description: Run the full prior suite against the survivor so a passing branch can't silently regress the system. Use when: Before reconcile.
---

# Regression Guarding

## Purpose
Run the full prior suite against the survivor so a passing branch can't silently regress the system.

## When to use
Before reconcile.

## How it fits PQA
Non-obvious branches are exactly the ones that surprise existing behaviour.
It serves the loop (frame -> superpose -> collide -> collapse -> precipitate) and the governing principle: spread probability mass into divergent
and low-probability branches, then collapse it onto whatever survives attack and verification.

## Discipline
Evidence over eloquence. Name what precipitates. Report confidence honestly. Never let a
persuasive rationale substitute for a passing test.
