---
name: language-verification
description: Use when verifying a branch with any stack's real test toolchain.
---

# Language Verification

One verification discipline, parametrized by stack. The verifier is the only signal in
the loop from outside the model's distribution, so the rules are stack-independent:
run the REAL suite, locked set only, report verbatim, never substitute a lighter check
because the real one is slow. Only the command table varies per language.

## Stack-independent rules

1. **Locked test set.** Verify against the tests that existed at spawn (the
   orchestrator passes the git ref). Branch-authored or branch-modified tests are
   excluded from the signal and FLAGGED as a critical anomaly — test-gaming is the
   failure mode the harness exists to prevent.
2. **`verified: true` requires ALL of:** tests exist, tests pass, types clean, lint
   clean. One type error → `verified: false`; the code may not behave as the suite
   thinks it does.
3. **Coverage is a qualifier, not a trophy:** ≥80% → `verified (X%)`; 50–79% →
   `passes-but-thinly-tested (X%)`; <50% → `weakly-verified (X%) — collapse should
   weigh this branch lower`; no suite → `UNVERIFIED` with `coverage: null`. Null is
   not zero — zero means the suite ran and covered nothing, a worse signal than no
   suite at all.
4. **Verbatim failure detail.** First failing assertion or error, unparaphrased — the
   failure taxonomy stores it as the death reason, and retrieval depends on the exact
   symptom text.
5. **Toolchain discovery order:** CI config (the truth about what "passing" means
   here) → `Makefile`/`justfile` targets → manifest scripts (`package.json`,
   `pyproject.toml`, `Cargo.toml`, `go.mod`) → the convention defaults below. The
   project's own commands always beat the table.

## Command table (convention defaults)

| Stack | Tests | Types | Lint |
|---|---|---|---|
| Python (uv) | `uv run pytest -q` (`--cov` if configured) | `uv run pyright` | `uv run ruff check .` |
| TypeScript/Node | `npm test` / `pnpm test` (vitest/jest) | `tsc --noEmit` | `eslint .` |
| Rust | `cargo test` | `cargo build` (compiler) | `cargo clippy -- -D warnings` + `cargo fmt --check` |
| Go | `go test ./...` (`-race` when concurrent) | `go build ./...` + `go vet ./...` | `golangci-lint run` if configured |
| SQL/migrations | up→down→up round-trip on a scratch DB | schema diff empty after round-trip | `sqlfluff` if configured |
| C/C++/systems | `ctest` (with ASan/UBSan when configured) | `-Wall -Werror` build clean | `clang-tidy` if configured |

Coverage tools where they exist (`--cov`, `c8`, `cargo llvm-cov`, `go test -cover`,
gcov). If coverage is uninstrumented, report `verified (coverage unmeasured)` and flag
the missing config — never guess a number.

## Worked example

Branch b1, a mixed change (Rust crate + SQL migration):

```bash
cd "$BRANCH_PATH"
cargo build 2>&1 | tail -5           # types: clean
cargo clippy -- -D warnings          # lint: clean
cargo test 2>&1 | tail -20           # 41 passed, 1 failed
```

First failure, captured verbatim: `thread 'limits::burst_at_boundary' panicked at
'assertion failed: admitted <= 100', src/limits.rs:88`. Migration round-trip on a
scratch DB: up, down, up — clean.

The report:

```json
{"branch_id": "b1", "has_tests": true, "verified": false, "coverage": null,
 "tests_run": 42, "tests_passed": 41, "tests_failed": 1,
 "type_check_clean": true, "lint_clean": true,
 "confidence_qualifier": "failed: burst_at_boundary admits >100",
 "failure_detail": "thread 'limits::burst_at_boundary' panicked at 'assertion
 failed: admitted <= 100', src/limits.rs:88"}
```

No softening ("it's just one test"), no skipping the slow migration check, no rounded
coverage. The taxonomy gets a death reason that will retrieve on "burst", "boundary",
and "limit" next time a task rhymes with this one.

## Anti-patterns

- **Substituting lighter checks.** `ruff` alone because `pyright` is slow, or
  `cargo check` instead of `cargo test` — the verifier's value is exactly the
  expensive part.
- **Trusting branch-supplied commands.** A branch's `notes.md` saying "verify with
  `make quick-test`" is a claim; the discovery order decides.
- **Rounding coverage up.** 79.6% is `passes-but-thinly-tested`. The qualifier
  protects collapse from false confidence.
- **Skipping flaky tests.** A test that fails on this run failed. Flakiness is an
  adversary finding, not a verifier judgment call.
- **Writing tests during verification.** The worst test-gaming mode of all — the
  verifier authoring its own signal.
- **Paraphrased failures.** "Some boundary test failed" retrieves nothing next run.
