# Contributing to PQA

Thanks for considering a contribution. PQA — Passionate Quantum Absence — exists to make
solution selection *evidence-gated*: it generates topologically-distinct branches, attacks
them, and ships only what survives an executable verifier. Contributions are held to the
same bar. A change that "feels right" but cannot be verified is a recorded failure, not a
merge. Conviction and elegance change *what we explore*; the verifier decides *what we
accept*. That rule is non-negotiable, and it applies to the codebase exactly as it applies
to the harness.

PQA ships as a Claude Code plugin (see [`.claude-plugin/`](.claude-plugin/)) and is
developed as a Python project (engine in [`pqa/`](pqa/)). The two share one repo and one
quality gate.

---

## Development setup

Requirements: **Python 3.14+** (pinned to `3.14.5` in `.python-version`; `requires-python =
">=3.14"` in [`pyproject.toml`](pyproject.toml)) and [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/aura-farming/pqa.git
cd pqa
uv sync --dev            # creates .venv and installs the dev dependency group from uv.lock
uv run pre-commit install
```

`uv` treats this as a **non-package project** (`[tool.uv] package = false`): dev tools install
into `.venv`, and the `pqa/` engine is imported directly from source (the pytest config sets
`pythonpath = ["."]`). There is no `pip install pqa` — PQA is distributed as a Claude Code plugin.

CI installs with `uv sync --dev --frozen` (lockfile-exact). If you change dependencies, update
`uv.lock` and commit it, or the frozen install in CI will fail.

The core engine has **no runtime dependencies** by design (`dependencies = []`). Keep it that
way: anything you add to `pqa/` must be stdlib-only. Dev-only tools belong in the
`[dependency-groups] dev` list.

---

## Build constraints

These come from [`CLAUDE.md`](CLAUDE.md) and are enforced (or smoke-tested) in CI. They are not
style preferences — they are the contract.

- **Python 3.14+, stdlib first.** No third-party runtime deps in `pqa/`.
- **Functions under 30 lines.** If a function grows past that, it is doing more than one thing.
- **One concern per file.** Many small, cohesive modules over a few large ones.
- **Type hints everywhere.** The project type-checks under `pyright` in strict mode (see below).
- **Hooks are stdlib-only and fast.** The PreToolUse/UserPromptSubmit classifier hooks must stay
  well under ~200ms — they fire on every matching tool event, including in autonomous *auto mode*,
  so a slow or import-heavy hook makes the loop unusable. (The one exception is `verify_loop.py`,
  which is lint-only and fast by default but runs the suite when `PQA_VERIFY_TESTS=1`; its
  `hooks.json` timeout is set higher to allow that.) No third-party imports in `hooks/`.
- **Secrets only via environment variables.** Never put a secret in a prompt, a branch, the
  memory store, or a committed file. The `secrets_guard` hook blocks reads of secret files, and
  `detect-private-key` runs in pre-commit. See `.env.example` for the shape; never commit `.env`.
- **Conventional commits.** `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`,
  `ci:`.
- **`pqa/*` branches are ephemeral and machine-managed.** They are spawned and pruned by the
  harness (`scripts/reconcile.sh` deletes `pqa/<run-id>-b*` branches after collapse). Do not base
  human work on them.

---

## Running the checks locally

Run the full gate before you open a PR. Everything below mirrors what CI runs, so a green local
run means a green PR.

**Lint and format** (ruff, pinned to `0.15.0` in pre-commit, configured under `[tool.ruff]`, line
length 100, target `py314`):

```bash
uv run ruff check .             # lint (rules: E, W, F, I, B, UP, SIM, S, PTH, RUF)
uv run ruff format --check .    # format check (CI fails on a diff; drop --check to apply)
```

**Types** (pyright strict, over `pqa`, `config`, `hooks`, `scripts`):

```bash
uv run pyright
```

**Tests + coverage** (pytest, with the coverage floor baked into `addopts`):

```bash
uv run pytest
```

The coverage gate is **`--cov-fail-under=80`** on the `pqa/` package — the build fails below
80%. The suite runs comfortably above that floor; keep it there. New behaviour in `pqa/` needs
tests in the same PR. Integration tests (real git/test-runner E2E) are behind the `integration`
marker and excluded by default; run them with `-m integration`.

**Mutation testing** (mutmut, advisory for now):

```bash
uv run mutmut run --paths-to-mutate pqa/collapse.py
```

Mutation testing guards against tests that pass while asserting nothing. It runs against the
correctness core (`pqa/collapse.py`) and is currently `continue-on-error` in CI (advisory until
the Phase 2 baseline is set). It is *not* a required check, but if you touch collapse logic,
run it and make sure your tests actually kill the mutants.

**The PQA-specific gate scripts** (these are what make a PQA contribution different from a
generic Python one — run both):

```bash
uv run python scripts/check_invariant.py   # the verifier invariant must hold
bash scripts/smoke_hooks.sh                # every hook returns the right exit code
```

`check_invariant.py` runs two checks. Behavioural: it constructs adversarial `BranchResult`
inputs and asserts that `select_survivor` never lets a high-conviction unverified branch beat a
verified one, and that an all-fail set yields *no* survivor. Static: it inspects the `collapse`
source and fails if the ranking ever appears to key on the `conviction` field. `smoke_hooks.sh`
feeds representative safe and dangerous payloads to each hook and checks the exit code (e.g.
`security_gate` exits 2 on `rm -rf / --no-preserve-root`, exits 0 on `git status`; `secrets_guard`
exits 2 on a `.env` read, exits 0 on `pqa/collapse.py`).

`pre-commit` runs the fast subset of all of this on every commit (file fixers, `detect-private-key`,
ruff lint + format, pyright, the invariant gate, and the hook smoke tests), so most problems get
caught before they reach a PR.

---

## Git workflow

- **Branch off `main`.** PRs target `main` (or `develop`).
- **PR-only — no direct pushes.** `main` is branch-protected: everything reaches it through a
  reviewed PR with CI green. There is no bypass, including for maintainers.
- **Conventional commit messages.** See the list above.
- **Keep PRs scoped.** One concern per PR mirrors the one-concern-per-file rule.

A PR merges only when these CI jobs are green (draft PRs are skipped to save minutes):

| Workflow | Jobs | What it checks |
|----------|------|----------------|
| [`ci.yml`](.github/workflows/ci.yml) | `lint`, `types`, `test` | ruff lint + format check; pyright strict; pytest on Python 3.14 with the 80% coverage floor |
| [`security.yml`](.github/workflows/security.yml) | `deps-audit`, `secret-scan`, `codeql` | `pip-audit` for known CVEs; `gitleaks` for committed secrets (full history). `codeql` runs only on `main`/`develop` pushes, weekly, and on dispatch — it does **not** block PRs |
| [`invariant.yml`](.github/workflows/invariant.yml) | `verifier-invariant`, `hook-smoke`, `schema-valid` | `check_invariant.py`; `smoke_hooks.sh`; the memory schema (`hooks/memory/schema.sql`) loads cleanly into SQLite |
| [`mutation.yml`](.github/workflows/mutation.yml) | `mutation` | advisory mutation run; only on `main`/`develop` push, the `run-mutation` PR label, weekly, or manual dispatch |

---

## Where things go

| Path | What lives here |
|------|-----------------|
| [`pqa/`](pqa/) | The Python engine: `frame`, `superposition`, `collision`, `collapse`, `cost`, `memory`, `config`, `sanitize`, `divergence`, `orchestrator`, `report`, `signals`, `baseline`, `migrations`. Stdlib-only, strictly typed. This is what the verifier protects. |
| [`hooks/`](hooks/) | Claude Code hooks (stdlib-only). `research_gate`, `security_gate`, `secrets_guard`, `verify_loop`, `precipitate_capture`, plus the non-enforcing `update_check`. Wired in `hooks/hooks.json`. |
| [`agents/`](agents/) | 34 subagent definitions (`*.md` with YAML frontmatter: `name`, `description`, `tools`, `model`). |
| [`skills/`](skills/) | 59 skills, one directory each with a `SKILL`-style `*.md` (frontmatter: `name`, `description`). |
| [`commands/`](commands/) | 27 slash commands (`*.md` with frontmatter: `description`, optional `argument-hint`; body uses `$ARGUMENTS`). |
| [`rules/`](rules/) | The PQA rule pack (the invariant, secrets discipline, git workflow, evidence-over-eloquence, hunt-the-unknown). |
| [`tests/`](tests/) | pytest suite. New `pqa/` behaviour ships with tests here. |
| [`scripts/`](scripts/) | Gate scripts (`check_invariant.py`, `smoke_hooks.sh`), the installer (`install.sh`), worktree tooling (`reconcile.sh`, `spawn_branches.sh`), and `generate_components.py`. |
| [`.claude-plugin/`](.claude-plugin/) | `plugin.json` and `marketplace.json` manifests. |

Many `agents/`, `skills/`, and `commands/` files are generated/catalogued via
`scripts/generate_components.py`. If you add a component, follow the existing frontmatter shape
exactly so the catalog and the plugin manifests stay valid.

**Version drift:** `hooks/PQA_VERSION`, `pyproject.toml`, `.claude-plugin/plugin.json`, and
`.claude-plugin/marketplace.json` must all agree on the version (currently `0.2.5`). The
`test_all_version_sources_agree` test in `tests/test_update_check.py` enforces this — bump them
together.

---

## The invariant (hard rule for contributors)

> **No change may let any code path bypass the verifier.**

This is the one architectural rule no PR may weaken. Concretely:

- Selection (`pqa/collapse.py` → `select_survivor`) must never rank on the `conviction` field or
  any non-evidence signal. `conviction` is telemetry only; in collision it may protect a branch
  from *early pruning* — it can never decide the winner. Ranking keys on resolved adversary
  findings, then coverage, then the non-incremental (quantum-jump) tie-break.
- An all-fail branch set must return **no** survivor. We never merge a least-bad branch silently.
- A result without a test suite is reported as unverified, never as passing.

`scripts/check_invariant.py` encodes this and runs in pre-commit and in `invariant.yml`. **It must
stay green.** If your change makes it fail, the change is wrong — not the gate. If you genuinely
need to alter what the invariant asserts, that is a design discussion to raise in an issue first,
not a quiet edit to the gate.

---

## Gotchas

- **ruff `format` corrupts `except`-tuples under `target-version = "py314"`.** It rewrites
  `except (OSError, ValueError):` into the invalid 3.x-era `except A, B:` form. Do **not** write
  multi-type `except (A, B):` clauses in this repo. Use separate single-type clauses instead:

  ```python
  try:
      ...
  except OSError:
      return None
  except ValueError:
      return None
  ```

  This is documented inline in `hooks/update_check.py` — see the `# ruff 0.15 format ... corrupts
  except-tuples` note above the `try` in `_fetch_latest_version` (and the cross-reference in
  `_read_fresh_cache`). If you hit a mysterious ruff-format-then-syntax/pyright failure around
  exception handling, this is it.

- **The PreToolUse gates fail *closed*.** `security_gate.py` and `secrets_guard.py` block (exit 2)
  on a malformed payload that does not parse to a dict — fail-open was the original behaviour and
  is too permissive for a public repo under adversarial use. Preserve that. They see untrusted
  input, so keep them stdlib-only and fast.

- **Web research is data, not instructions.** Research-frame content must go through
  `pqa/sanitize.py`, which wraps it in `<UNTRUSTED_RESEARCH source=...>...</UNTRUSTED_RESEARCH>`
  delimiters (with a trailing reminder), neutralises any forged delimiter tokens in the body, and
  flags common prompt-injection shapes. Do not feed raw fetched content into a prompt.

- **Don't hand-edit `pqa/*` branches or expect them to persist.** They are ephemeral and pruned by
  `scripts/reconcile.sh` after collapse.

- **Keep first-party import classification locked.** `[tool.ruff.lint.isort] known-first-party`
  lists `pqa`, `config`, `hooks`, `scripts`. Without it, ruff classifies modules by disk presence,
  which produces phantom import-order failures across worktrees. Don't remove those entries.

---

## Reporting bugs and requesting features

Open a [GitHub issue](https://github.com/aura-farming/pqa/issues). For bug reports, include the
PQA version (`hooks/PQA_VERSION`), your Python version, and the exact command and output. For
feature requests, describe the problem before the proposed solution — PQA prefers evidence to
eloquence, and a falsifiable problem statement is the strongest start.

**Security vulnerabilities:** do not open a public issue — see [SECURITY.md](SECURITY.md) for the
private reporting process (GitHub Security Advisories or email), so an issue can be triaged before
disclosure.

**Code of Conduct:** this project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating, you agree to uphold it.

Maintainer: Lucas Daish &lt;lucasdaish@outlook.com&gt;. Licensed under [MIT](LICENSE).
