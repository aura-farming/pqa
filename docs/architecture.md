# PQA Architecture

PQA is co-precipitation made executable: hold divergent solutions in tension, attack them,
converge only on what survives attack AND tests.

## Component map

- `.claude/CLAUDE.md` — the operating frame, loaded into every session. The one unbreakable
  rule lives here: nothing merges without passing the verifier.
- `.claude/agents/` — five subagents, one role each:
  orchestrator (runs the loop, judges on evidence), researcher (research frame),
  generator (one divergent branch, blind to siblings), adversary (breaks branches),
  verifier (the empirical collapse gate).
- `.claude/commands/` — `/pqa` (full loop), `/superpose` (branches only), `/collapse`
  (collide+converge), `/precipitate` (name + persist).
- `.claude/hooks/` — research_gate (dual-frame protocol injection), security_gate (blocks
  destructive/exfil ops, exit 2), secrets_guard (blocks subagents reading .env/keys, exit 2),
  verify_loop (lint/test after every edit, exit 2 on fail), precipitate_capture (persists
  precipitates + failures on SubagentStop).
- `.claude/memory/schema.sql` — precipitates, failures, signals, frames.
- `pqa/` — Python core: `collapse.py` (survivor selection — correctness heart),
  `signals.py` (conviction parsing), `memory.py` (persistence), `superposition.py` +
  `collision.py` (Phase scaffolds).
- `scripts/` — `spawn_branches.sh` / `reconcile.sh` (git-worktree parallelization),
  `check_invariant.py` + `smoke_hooks.sh` (CI gates).
- `.github/workflows/` — `ci` (lint/types/tests), `security` (pip-audit/gitleaks/CodeQL),
  `invariant` (verifier-bypass guard, hook smoke, schema, mutation). Dependabot keeps deps latest.

## The loop, in one line each

frames load (research × self-eval) → superpose N divergent branches → adversary collides →
verifier collapses on evidence → name + persist precipitate and failure taxonomy.

## The honesty invariant

Conviction changes WHAT is explored, never WHAT is accepted. A high-conviction branch that
fails verification is recorded as a failure (the most valuable data the system makes), never
merged. Coverage is reported as a confidence qualifier on every result. No suite → result is
labelled UNVERIFIED. This invariant is what separates breakthrough from theatre.
