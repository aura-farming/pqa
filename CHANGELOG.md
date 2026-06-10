# Changelog

All notable changes to PQA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-10

The world-class revamp: corrected economics, context discipline, a deep surface, the
learning moat wired end-to-end, a falsifiable benchmark, and engine-owned worktrees.

### Added
- **Worktree Phase 1, engine-owned** (`pqa/worktrees.py`): one isolated git worktree
  per branch on ephemeral `pqa/<run>-bN` branches, with a **write-ahead registry** in
  `.pqa/state.json` so strays survive even a mid-run SIGKILL; rollback on partial
  spawn; `reconcile()` merges `--no-ff`, aborts on conflict preserving the survivor
  branch, and always prunes. `Branch.workdir` + `run(workdirs=...)` thread isolation
  through the engine; `spawn_branches.sh` / `reconcile.sh` became thin engine callers;
  the orchestrator and reconciler honor `branches_mode = "worktree"` with a stray
  sweep at init. Zero-orphan recovery is a tested invariant.
- **Locked eval benchmark**: 8 tasks under `evals/tasks/` (each `task.toml` + LOCKED
  `verify.py` + `reference.py` must-pass + `sabotage.py` must-fail) and
  `scripts/eval_harness.py` (deterministic `score`/`report`/`smoke`, zero model
  calls); `/eval` and `pqa-eval-runner` wired to it; nightly `eval-smoke` workflow
  re-proves verifier integrity. The README documents the methodology; live numbers
  land only from a live run — losses included.
- **The learning moat, wired**: conviction signals get their outcomes back-filled
  post-collapse; `pqa/instincts.py` synthesizes instincts from precipitates+failures
  (overlap clustering; confidence from support and contradictions); prior-art injects
  top instincts; `RunReport` carries `instincts_injected` and per-instinct agreement;
  the dashboard gains calibration + instincts sections; the self-reflector reads the
  engine's `calibration()`.
- **Run resume**: crash-resumable run journal (`pqa/state.py` → `.pqa/state.json`,
  atomic tmp+rename) — `/pqa --resume` re-enters at the first incomplete stage.
  Journal writes preserve foreign top-level keys (the file is shared with the
  worktree registry).
- **Generated configuration reference**: `docs/configuration.md` rendered from
  `pqa/config.py` by `scripts/generate_config_doc.py`, drift-pinned by tests.

### Changed
- **Economics corrected; tokens primary**: cost-model defects fixed, model aliases
  (`fable`/`opus`/`sonnet`/`haiku`) wired to real pricing/dispatch via
  `pqa.cost.resolve_model`, budgets token-primary with USD secondary, and a
  pre-flight `would_abort` gate before every dispatch (not just after the spend).
- **Model routing per role**: Fable 5 where output quality is decided (generators,
  unknown-scout, adversary, collapse-judge, baseline control); sonnet/haiku for
  mechanical and bookkeeping tiers. "Every agent on Opus" is gone from docs and
  dispatch.
- **Context discipline in the orchestrator**: branch payloads live on disk and are
  read only by the subagent that needs them; the orchestrator holds ≤200 tokens of
  state per branch (digests only) and reports per-stage context telemetry.
- **Surface: depth over breadth** — 34 agents · 59 skills · 27 commands trimmed to
  **14 agents · 12 commands · 12 deep skills** (each skill a protocol + worked
  example + anti-patterns playbook); `validate_components.py` gained census, depth,
  and description-budget gates and drift-gates `docs/catalog.json`.
- **Memory retrieves by relevance** under a hard token budget (not recency), and
  every injected memory id is reported per run.
- **Docs truth pass**: README (counts, hook claims, stage wording, workflow count,
  status), architecture.md (rewritten to the shipped reality), CONTRIBUTING and the
  plugin manifests; hooks language unified with SECURITY.md (two blocking hooks,
  the rest fail open; the binding guarantee lives in CI).

### Fixed
- Hook hardening: per-hook kill-switches (`PQA_DISABLED_HOOKS`), once-per-session
  research gate, fail-closed fixes on the security/secrets gates.

## [0.2.5] — 2026-05-29

### Added
- **Update notice**: a `SessionStart` hook (`hooks/update_check.py`) prints a one-line banner when a newer PQA release exists (`⬆️  PQA <new> available — you have <current>`). The GitHub Releases check is cached for 24h, times out fast, fails silent offline, and never blocks a session. Stdlib-only. Installed version ships in `hooks/PQA_VERSION` so both plugin and manual installs can self-identify.
- Version-drift guard test: `hooks/PQA_VERSION`, `pyproject.toml`, and both plugin manifests must agree.

## [0.2.4] — 2026-05-29

### Security
- **security_gate**: block secret reads via `xxd`/`od`/`hexdump`/`strings`/`dd`/`sed`/`awk`/`grep`/`egrep`/`fgrep`. The previous list only matched `cat`/`less`/`head`/etc., so a byte reader or stream processor (`strings id_rsa`, `xxd .env`, `grep KEY .env`) trivially bypassed the gate. Readers are blocked only when they target a secret path; boundary tests pin the false-positive line.
- **sanitize**: neutralize forged `</UNTRUSTED_RESEARCH>` / open-prefix delimiters embedded in research content, so untrusted web text can no longer close the wrapper early and have following text read as instructions. Non-stripping — the payload stays visible and the forgery is flagged.

### Added
- End-to-end tests for the quantum-jump tie-break through `orchestrator.run()`: a true tie breaks toward the non-incremental branch, and higher coverage still wins (evidence beats the quantum-jump preference — it is the last tiebreak key, not a promotion).

### Fixed
- `scripts/install.sh` no longer instructs users to set `ANTHROPIC_API_KEY` — PQA runs on the Claude Code subscription; no key is needed.
- `pqa/config.py`: corrected the `model` comment that claimed an alias→`MODEL_PRICING` translation which does not exist; documents that `model` is a declared preference not yet wired to dispatch/pricing, and flags the latent `KeyError` trap.

### Changed
- Cross-referenced the conviction regex duplicated between `pqa/signals.py` and the `precipitate_capture` hook (the hook is stdlib-only and cannot import `pqa`, so the duplication is intentional — "change both together").
- Aligned the package version across `pyproject.toml` and the plugin manifests.

## [0.2.3] — 2026-05-28

### Changed
- Plugin manifest: drop `agents`/`hooks`/`rules` from explicit paths (rely on auto-discovery), `mcpServers={}`, container fields expressed as arrays.

## [0.2.2] — 2026-05-28

### Changed
- Plugin manifest: `author` expressed as an object; container fields as arrays.

## [0.2.1] — 2026-05-28

### Fixed
- Plugin made installable by anyone: MIT license, schema-valid manifests.

[0.3.0]: https://github.com/aura-farming/pqa/compare/v0.2.5...v0.3.0
[0.2.5]: https://github.com/aura-farming/pqa/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/aura-farming/pqa/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/aura-farming/pqa/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/aura-farming/pqa/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/aura-farming/pqa/releases/tag/v0.2.1
