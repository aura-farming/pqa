# PQA — Passionate Quantum Absence

> A Claude Code plugin that forces divergent solution generation and adversarial verification into every coding task. It collapses probability mass onto high-value action sequences — including the low-probability ones, because the unknown is where the highest achievement lives.

PQA is not another autocomplete. It refuses the single-pass default — the most *probable* answer, which is the generic one — and instead spreads effort across genuinely different approaches (superposition), attacks each (collision), and converges only on what survives attack **and** tests (collapse). Every agent runs on **Opus (latest)**.

## What you get

- **34 agents**, **59 skills**, **27 commands** — every one PQA-native, none generic. They serve one loop: `frame → superpose → collide → collapse → precipitate`.
- The unbreakable invariant: **nothing merges without passing the verifier.** Conviction changes what is *explored*, never what is *accepted*.
- **Three continuous loops:** precipitation (every run names + persists what won), human learning (export/import instincts to share judgement across people), and self-understanding (the harness calibrates its own conviction against outcomes).
- Five enforcing hooks: research gate, security gate, secrets guard, verify loop, precipitate capture.

## Install

PQA installs three ways. **No API key needed** — it runs on your existing Claude Code subscription. Every agent runs on Opus; mind your plan usage (`/budget` is a guardrail). PQA is built for **auto mode** (autonomous, classifier-gated) — the hooks keep that safe by blocking dangerous ops even when prompts are off.

**As a plugin (recommended):**
```
/plugin marketplace add aura-farming/pqa
/plugin install pqa@pqa-marketplace
```

**Manually, project-level** (just this repo):
```bash
git clone https://github.com/aura-farming/pqa.git && cd pqa
./scripts/install.sh project      # installs into ./.claude
```

**Manually, system-level** (all your projects):
```bash
./scripts/install.sh system       # installs into ~/.claude
```

Then open Claude Code in your project and run `/pqa <task>`.

## The loop, in commands

`/frame` (load research vs self-eval) → `/superpose` (divergent branches, one into the unknown) → `/collapse` (attack + verify + converge) → `/precipitate` (name + persist). Or just `/pqa <task>` to run the whole thing. `/baseline` captures the single-pass result so you can measure the difference; `/spiral` goes another round; `/eval` benchmarks against the baseline over time.

Learning is portable: `/instinct-status` shows what PQA has learned (with confidence), `/instinct-export` / `/instinct-import` share instincts across people, `/evolve` clusters them into skills, and `/dashboard` renders the accumulating moat.

## Configuration

PQA reads runtime settings from `pqa-config.toml` (TOML) and / or `PQA_*`
environment variables. Precedence is **env > TOML > built-in defaults**.

```python
from pqa.config import load_or_defaults
cfg = load_or_defaults()          # reads ./pqa-config.toml if present
cfg = load_or_defaults("custom.toml")  # explicit path; falls back to defaults if missing
```

For a strict-required-file entry point, use `load_config(path)` — it raises
`FileNotFoundError` when the file is absent. See `pqa-config.example.toml`
for the full schema with comments. The loader is stdlib-only (`tomllib`),
strictly typed, and rejects:

- wrong-typed values (`branches = "seven"`)
- unknown keys in `[pqa]`
- non-finite or non-positive `run_budget_usd` (closes a cost-tracker bypass)
- `memory_db` paths into system directories (`/etc`, `/var`, etc.)

See `tests/test_config.py` for the locked behavioural contract (24 tests
covering type discipline, precedence, error chaining, and security guards).

## How it's built

Python 3.14.5 (stdlib-only harness core) · uv + pyproject.toml · Claude Code plugin (agents/skills/commands/hooks + `.claude-plugin/` manifests) · git worktrees for parallel branches · SQLite (WAL) for memory · ruff 0.15 / pyright 1.1.409 strict / pytest 9 + mutmut as the collapse gate. Three CI workflows gate every change; Dependabot keeps the toolchain at latest. Every agent: `model: opus`.

## Status

`Draft` — Phase 0. Engine core (`collapse`, `signals`, `memory`) implemented and tested (16 tests, 95% coverage); invariant gate and hook smoke tests passing; instinct export/import working; full component catalog (34/59/27) generated. Next: the cost-governor budget cap and the single-pass baseline comparator, then true worktree parallelization.

## Licence

MIT. See [LICENSE](LICENSE).
