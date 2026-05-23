---
name: rust-verification
description: Verify Rust branches: cargo test, clippy, miri where relevant, coverage. Use when: Collapsing Rust branches.
---

# Rust Verification

## Purpose
Verify Rust branches: cargo test, clippy, miri where relevant, coverage.

## When to use
Collapsing Rust branches.

## How it fits PQA
The Rust arm of the verifier.
It serves the loop (frame -> superpose -> collide -> collapse -> precipitate) and the governing principle: spread probability mass into divergent
and low-probability branches, then collapse it onto whatever survives attack and verification.

## Discipline
Evidence over eloquence. Name what precipitates. Report confidence honestly. Never let a
persuasive rationale substitute for a passing test.
