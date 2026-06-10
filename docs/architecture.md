# PQA Architecture

PQA is co-precipitation made executable: hold divergent solutions in tension, attack them,
converge only on what survives attack AND tests.

## Component map

- `CLAUDE.md` — the operating frame, loaded into every session. The one unbreakable
  rule lives here: nothing merges without passing the verifier.
- `agents/` — 14 subagents, one role each, model-routed per role (Fable 5 exactly
  where output quality is decided): pqa-orchestrator (runs the loop — sonnet
  plumbing); the fable tier — pqa-generator (one divergent branch, blind to
  siblings), pqa-unknown-scout (the forced low-probability branch), pqa-adversary
  (breaks, never fixes), pqa-collapse-judge, pqa-baseline-runner (fair single-pass
  control); the mechanical tier — pqa-verifier (the empirical collapse gate),
  pqa-reconciler, pqa-frame-loader (sonnet); and the bookkeeping tier —
  pqa-memory-curator, pqa-failure-taxonomist, pqa-eval-runner (haiku), plus
  pqa-instinct-synthesizer and pqa-self-reflector over the learning store.
- `commands/` — 12 thin commands: `/pqa` (the full loop, scaled to the ask;
  `--resume` re-enters a crashed run), `/attack` and `/verify` (collision and
  verification gates standalone), `/baseline` and `/eval` (falsifiability),
  `/cost`, `/budget`, `/dashboard`, `/memory`, `/instinct-export`,
  `/instinct-import`, `/install`.
- `skills/` — 12 deep playbooks (protocol + worked example + anti-patterns each),
  depth-gated by `scripts/validate_components.py`; `docs/catalog.json` is
  drift-gated against the files on disk.
- `hooks/` — five hooks, honestly split (see SECURITY.md): security_gate and
  secrets_guard hard-block with exit 2 even in auto mode; verify_loop feeds
  lint/test failures back after edits; research_gate (dual-frame injection) and
  precipitate_capture (persists outcomes on SubagentStop) are advisory/fail-open.
  `hooks/memory/` holds the SQLite store managed by `pqa/migrations.py`.
- `pqa/` — the stdlib-only engine: `orchestrator.py` (the deterministic loop),
  `frame.py`, `superposition.py` + `divergence.py` (topology-diverse spawning and
  the lookalike gate), `collision.py` (finding scores), `collapse.py` (survivor
  selection — correctness heart), `cost.py` (token-primary governor + model
  aliases), `memory.py` + `instincts.py` + `signals.py` (the learning moat:
  precipitates, failures, conviction outcomes, synthesized instincts),
  `state.py` (crash-resumable run journal in `.pqa/state.json`), `worktrees.py`
  (engine-owned worktree lifecycle, write-ahead registry in the same state file),
  `baseline.py`, `report.py`, `sanitize.py`, `migrations.py`, `config.py`.
- `scripts/` — `spawn_branches.sh` / `reconcile.sh` (thin CLI callers of
  `pqa.worktrees`), `validate_components.py` (census + depth gates + catalog),
  `eval_harness.py` (deterministic benchmark scoring, zero model calls),
  `generate_config_doc.py` (renders docs/configuration.md from config.py),
  `dashboard.py`, `tune.py`, `check_invariant.py` + `smoke_hooks.sh` (CI gates).
- `evals/tasks/` — 8 locked benchmark tasks (task.toml + LOCKED verify.py +
  reference.py must-pass + sabotage.py must-fail); integrity re-proven on every
  push and nightly.
- `.github/workflows/` — five: `ci` (lint/types/tests), `security`
  (pip-audit/gitleaks/CodeQL), `invariant` (verifier-bypass guard, hook smoke,
  schema, mutation trigger), `mutation`, `eval-smoke` (nightly verifier
  integrity).

## Branch execution modes

`branches_mode = "context"` (default): branches run in-context, sequentially — no git
required. `branches_mode = "worktree"`: `pqa/worktrees.py` spawns one isolated git
worktree per branch on an ephemeral `pqa/<run>-bN` branch. The registry is written to
`.pqa/state.json` BEFORE the first git mutation, so a mid-run kill leaves strays
findable (`registered()`); a partial spawn rolls itself back; `reconcile()` merges the
survivor `--no-ff` (abort on conflict, survivor branch preserved) and always prunes —
zero orphans is a tested invariant, not an aspiration. Generators write into their
tree (`Branch.workdir`); verifiers run the real suite inside it, so parallel
verification cannot race on one shared tree.

## The loop, in one line each

frames load (research × self-eval) → superpose N divergent branches → adversary collides →
verifier collapses on evidence → name + persist precipitate and failure taxonomy.

## The honesty invariant

Conviction changes WHAT is explored, never WHAT is accepted. A high-conviction branch that
fails verification is recorded as a failure (the most valuable data the system makes), never
merged. Coverage is reported as a confidence qualifier on every result. No suite → result is
labelled UNVERIFIED. This invariant is what separates breakthrough from theatre.
