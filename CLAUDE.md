# PQA — Passionate Quantum Absence

This repo runs the PQA harness. PQA is co-precipitation made executable for code:
hold divergent solutions in tension, attack them, and converge only on what survives
attack **and** tests. The goal is non-obvious solutions that are also correct.

**Governing principle: collapse probability mass onto high-value action sequences** — not the
most *probable* sequence (that's the generic single-pass default), but the highest-*value* one,
which is usually not the most probable. Superposition spreads the mass wide across divergent
approaches; collision and verification concentrate it onto the path with the highest demonstrated
value. Low probability is not low value — confusing the two is the failure PQA exists to prevent.
"High-value" is operational, not vibes: passes verification, resolves the most adversary findings,
and is a path a single pass would not have taken.

**Corollary: the highest achievement lives in the low-probability region — the unknown.** The
high-probability path is the generic average; breakthrough sits in low-probability space almost by
definition. If probability is low, the unknown can happen — so reach into it on purpose (the forced
P_reframe branch, conviction protecting low-probability branches from pruning). This is a bet with
bounded downside (one cheap ephemeral worktree, discarded if it fails) and uncapped upside (if it
verifies). Explore the unknown freely; let the verifier capture the value only when it proves real.
Reaching is exploration; accepting is earned.

## The one rule that cannot be broken

**Nothing reaches a merge without passing the verifier.** Conviction, elegance, and
"it feels right" change *what gets explored*, never *what gets accepted*. A high-conviction
branch that fails tests is a recorded failure, not a shipped feature. This is not caution
for its own sake — an unverified coding harness produces confident wrong code, which is the
opposite of higher intelligence. The verifier is the external perturbation that keeps the
field honest. It stays.

## The loop

1. **Load two frames.** Research frame (what docs/web say is right) and self-eval frame
   (what is true *in this context*). Log where they disagree — the gap is the first
   collision and the first branching axis.
2. **Superpose.** Spawn N branches (default 3) that differ in *topology* — architecture,
   data model, control flow — not in style. Generators work blind to each other so they
   don't converge early. At least one branch must take the non-obvious fork (P_reframe).
3. **Collide.** The adversary attacks every branch: edge cases, failure modes, security,
   unjustified complexity, broken assumptions. It breaks, it does not fix.
4. **Collapse.** The verifier runs the real tests/types/lint. The survivor is the branch
   that passes verification and resolves the most adversary findings. Ties break toward the
   less incremental branch (the quantum jump).
5. **Name & persist.** Name the winning precipitate and why it won; record every dead branch
   and why it died. This is continuous learning — next run's frames are sharper for it.

## Quantum vocabulary → real operations (no metaphysics)

- **Superposition** = N genuinely different live solutions before any choice. Different in
  *kind*, or it's just expensive noise.
- **Wormhole / "feels right"** = a `conviction: high` flag on a branch. Effect: that branch
  is **protected from early pruning** in collision. It still goes through the verifier.
  Honour the instinct by exploring it fully; let evidence decide.
- **Quantum jump** = when branches tie on correctness, pick the bigger defensible swing.
- **Relativity** = hold a branch as *simultaneously* possibly-breakthrough and possibly-noise.
  Never declare which from inside. The verifier collapses it with evidence. Useful beats profound.

## Perturbation operators

- **P_collapse** — name a rigid assumption and pressure it.
- **P_reframe** — produce at least one branch from a refused frame.
- **P_deepen** — when output is surface-level, demand self-eval over restated research.
- **P_name** — name every precipitate before merging; unnamed insight dissolves.

## Honesty rules

- Report test coverage as a confidence qualifier on every converged result. Never imply
  certainty the tests can't support.
- If all branches fail, say so. Do not merge a least-bad branch silently.
- If there is no test suite, collapse on adversary findings only and **flag the result as
  unverified**. Recommend tests.
- Record where conviction and reality diverged — that is the most valuable data the system makes.

## The three continuous loops

PQA never stops at one run. Three loops compound across runs and across people:

1. **Continuous precipitation** — every run names and persists its winning insight, so the
   precipitate registry grows continuously, not per-session. Named insight compounds; unnamed
   insight dissolves.
2. **Continuous learning (human)** — instincts synthesised from many runs are exportable and
   importable (`/instinct-export`, `/instinct-import`). Learning crosses *people*, not just
   sessions; your judgement becomes portable and a teammate's instincts become yours.
3. **Continuous self-understanding (the harness)** — PQA reflects on its own history via
   `pqa-self-reflector`: how well its conviction signals are calibrated against outcomes, where
   its recurring blind spots are, and where it genuinely beats a single pass. The harness learns
   about its own learning, so you trust the right instincts and discount the rest.

## Run mode

PQA delegates heavily to subagents and runs many tool calls (worktrees, tests, lint), so it is
built for **autonomous operation** — Claude Code **auto mode** (recommended), or
bypass-permissions only inside a sandbox. Interactive prompting on every call would make the loop
unusable. The five hooks are what make autonomous running safe: they fire on tool events
regardless of permission mode and exit-2 *block* dangerous operations even when permission prompts
are off. In auto mode they complement the classifier; in bypass mode they are your guardrail.

No API key is needed — PQA runs on the user's Claude Code subscription via the project- or
user-scope install.

## Build constraints (Risen standard)

Python 3.14+, stdlib first. Hooks stdlib-only, <200ms. Type hints everywhere. Functions
under 30 lines. One concern per file. Secrets only via env; never in a prompt, branch, or
the memory store. Conventional commits. `pqa/*` git branches are ephemeral and machine-managed.
