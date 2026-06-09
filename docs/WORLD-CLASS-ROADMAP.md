# PQA World-Class Roadmap

> Full-harness review, June 2026. Scope: everything — engine, plugin surface, hooks, memory,
> docs, and mission — judged against two explicit bars: **perfect context management** and
> **operational efficiency at parity with ECC (Everything Claude Code)**.
>
> PQA's one purpose is to enhance agents and Claude Code itself. Every recommendation below
> is in service of that purpose, ordered by priority. Each item has an acceptance test so
> "done" is checkable, in PQA's own spirit: evidence over eloquence.

---

## 1. Verdict

**The thesis is sound and differentiated. The engine is real. The surface is hollow. The
economics are mis-wired. The moat is unproven.**

What PQA gets right, and must protect:

- **The mission is crisp and falsifiable.** "Structured test-time compute for code, with a
  hard verifier gate" is a real, defensible position. Nothing else in the Claude Code plugin
  ecosystem enforces *verifier-gated multi-branch convergence*. ECC is a toolbox; PQA is a
  method. That focus is the moat — do not trade it for ECC's breadth.
- **The Python engine is genuinely good.** `pqa/` is small, typed, stdlib-only, migration-managed,
  and tested above an enforced 80% branch-coverage floor. `collapse.select_survivor` has a CI
  invariant gate (`scripts/check_invariant.py`) that statically forbids conviction from entering
  the ranking — that is world-class discipline for the one rule that cannot break.
- **The honesty rules are the right rules.** UNVERIFIED flagging, all-branches-fail honesty,
  conviction-vs-reality calibration as first-class data.

What stands between this and world-class:

| # | Problem | Severity |
|---|---|---|
| 1 | A default run **cannot complete under its own cost gates** (wrong pricing × pessimistic projections × inconsistent budget defaults) | P0 |
| 2 | Orchestrator context is unbounded — all N branch outputs are interpolated inline twice (adversary, judge) | P0 |
| 3 | 59 of 59 skills and 26 of 34 agents are template stubs with no operational content | P0 |
| 4 | Every agent runs on Opus, including pure-bookkeeping agents; zero model routing | P1 |
| 5 | ~3,000 tokens of agent+skill descriptions taxed on every session; research-gate injects on nearly every prompt with no off-switch | P1 |
| 6 | The learning moat (signals, instincts, self-reflection) is mostly unwired — the tables exist, nothing writes them | P1 |
| 7 | The headline claim ("beats single-pass, falsifiably") has never been demonstrated — no published eval results | P1 |
| 8 | Worktree parallelization — the central architectural promise — is not implemented | P2 |

---

## 2. North-star principles

These are the design laws every change below follows. Adopt them as repo policy.

1. **Context is the scarcest resource. Every injected token must pay rent.**
   A harness that burns the user's context window to describe itself is anti-enhancement.
2. **Files are the data plane; digests are the control plane.**
   Full branch outputs live on disk (eventually: in worktrees). Conversations carry bounded
   summaries and artifact paths, never payloads.
3. **The model tier must match the job.** Judgment work (generate, attack, judge) earns the
   top model. Bookkeeping (cost math, reporting, registry writes) never does.
4. **Everything the harness asks of others, it does itself.** PQA demands evidence from
   branches; it must publish evidence for its own win-rate claim.
5. **Every gate must be escapable and say how.** Blocking hooks need a documented,
   user-controlled disable path (ECC's `ECC_DISABLED_HOOKS` / `ECC_GATEGUARD=off` pattern).
   A guardrail with no override is a trap, not a guardrail.

---

## 3. P0 — Correctness: make a default run actually complete

### 3.1 Fix the cost model (three compounding defects)

**Files:** `pqa/cost.py`, `pqa/config.py`, `agents/pqa-orchestrator.md`

1. **Pricing table is wrong.** `pqa/cost.py:21` prices `claude-opus-4-7` at $15/$75 per MTok.
   Actual Opus 4.7/4.8 pricing is **$5/$25**; Haiku 4.5 is $1/$5 (table says $0.80/$4).
   Opus cost is overstated 3×. Add current models (Opus 4.8 at minimum), and add a comment
   discipline + test that pins pricing to a dated source, or fetch from the Models API when
   available and fall back to constants.
2. **Budget defaults disagree.** `pqa/config.py:37` defaults `run_budget_usd = 15.0`; the
   orchestrator prompt (`agents/pqa-orchestrator.md` §"The loop") says `budget_usd (default 2.0)`.
   Pick one (recommend: $5 with routing from §5, which comfortably fits N=3) and derive the
   orchestrator's number from config, never hardcode it in a prompt.
3. **The math self-aborts.** Pre-flight projection per Opus dispatch = 50k-token input floor +
   16k output = ~$1.95 at the (wrong) $15/$75 pricing. A full N=3 run needs ~10 dispatches.
   At a $2 budget the run aborts on dispatch #2; even at $15 it cannot finish if anything runs
   long. Meanwhile actual recording uses `_DEFAULT_MODEL = "claude-sonnet-4-6"`
   (`pqa/orchestrator.py:114`) for work that really runs on Opus — so projections over-block
   and actuals under-count. **Fix:** one model-identity source of truth flowing from agent
   frontmatter → dispatch → projection → recording.
4. **Budget in tokens, display in USD.** PQA runs on the Claude Code subscription (no API key),
   so USD is synthetic; the real constraints are tokens, rate limits, and context. Make the
   governor's primary ledger token-based (`run_budget_tokens`), keep USD as a derived display
   for API-mode users.

**Acceptance:** `uv run python examples/phase0_demo.py` extended with realistic per-dispatch
projections completes N=3 under the default config; a unit test asserts a simulated full run
(frame + N gen + adversary + N verify + judge + reconcile) fits the default budget; pricing
table has a test pinning it to documented rates.

### 3.2 Wire `cfg.model` or delete it

`config.py` validates `model ∈ {opus, sonnet, haiku}` but the value is never used for dispatch
or pricing (the alias keys are disjoint from `MODEL_PRICING` keys — and
`tests/test_config.py::test_model_allowlist_matches_cost_pricing_aliases` enforces the
*disjointness*, codifying the bug). Either implement alias→concrete-model mapping that drives
agent dispatch and pricing, or remove the field. A config knob that changes nothing is worse
than no knob.

### 3.3 Engine and script defects

| Fix | File | Detail |
|---|---|---|
| Sanitize `session_id` before using as a path | `pqa/report.py` (`write_report`) | Path separators in `session_id` escape the artifact root. Validate `^[A-Za-z0-9._-]+$`. |
| Create `.pqa/` before first use | `scripts/install.sh` + orchestrator step 0 | All file handoffs (`frame.json`, `spawn_prompts.json`, `findings.json`, `artefacts/`) assume it exists. |
| Single schema source | `scripts/install.sh` vs `pqa/migrations.py` | install.sh seeds from `hooks/memory/schema.sql`, the engine migrates from `hooks/memory/migrations/`. They will drift. Make install run the migration runner; delete `schema.sql`. |
| Fail closed, loudly | `hooks/secrets_guard.py` (bare `except: pass` ×4) | Silent exception swallowing in path/symlink resolution **fails open** — the opposite of the hook's stated design. Log to stderr and block on resolution failure. |
| Stop losing precipitates silently | `hooks/precipitate_capture.py` (bare `except: pass` ×2) | DB write failures silently drop the moat's input data. Write to the JSONL fallback on DB failure and emit one stderr warning. |
| Implement `respawn-pair` | `pqa/orchestrator.py` (~line 249) | The divergence gate can return `respawn-pair` but the orchestrator only handles `abort` — collapsed superpositions proceed unfixed, which silently voids the diversity guarantee. Honor the plan (one respawn, then proceed/abort). |
| Cleanup on partial spawn failure | `scripts/spawn_branches.sh` | Trap errors and remove already-created worktrees; otherwise orphans accumulate. |
| Abort merge on conflict | `scripts/reconcile.sh` | A conflicted merge currently prints and continues, leaving the repo mid-merge. `git merge --abort` and exit non-zero. |
| Lock the update-check cache | `hooks/update_check.py` | Concurrent sessions race on `~/.cache/pqa/update_check.json`. Use atomic write (tmp + rename). |
| Fix `/pqa` in the build-intent regex | `hooks/research_gate.py:19` | `\b/pqa\b` can never match at prompt start (`\b` needs a word char before `/`). The explicit trigger is the one input that doesn't fire the gate. |

**Acceptance:** `scripts/smoke_hooks.sh` extended to cover the fail-closed paths and the
`/pqa`-prefix prompt; a test creates a worktree spawn failure mid-way and asserts zero orphans.

---

## 4. P1 — Context management (the core ask)

Target state, measurable: **fixed per-session tax < 1,000 tokens; orchestrator peak context
< 20k tokens for N=3 on a real task; zero unbounded interpolations.**

### 4.1 Stop carrying branch payloads in the orchestrator

Today (`agents/pqa-orchestrator.md` steps 4 and 6): all N full branch outputs are interpolated
into the adversary prompt (`${BRANCH_OUTPUTS}`), and full branch state again into the judge
prompt (`${BRANCH_STATE_JSON}`). With three substantive solutions this is 30–80k tokens
resident in the orchestrator and re-paid in every downstream dispatch.

**Redesign — files as data plane, digests as control plane:**

1. Generators **write** their full output to `.pqa/branches/bN/` (Phase 1: the worktree) and
   **return** only a bounded digest: `{branch_id, topology_axis, approach (≤3 sentences),
   files_touched, loc, conviction?}` — ≤150 tokens, schema-enforced.
2. The adversary is dispatched **per branch, in parallel** (same single-message parallelism
   already used for generators), with the branch *path*; it `Read`s the code itself inside its
   own context and returns findings JSON only. This simultaneously fixes the mega-prompt and
   un-serializes the slowest stage. Cross-branch comparison, where genuinely needed, is a
   second cheap pass over findings — not over code.
3. The collapse judge receives **digests + findings + verifier results only** — never raw code.
   The engine's `select_survivor` already corroborates on structured data; the judge's job is
   P-relativize over evidence, which doesn't require payloads.
4. The orchestrator never echoes payloads back into its own reasoning. Its context budget per
   stage is written into its prompt as a contract ("hold ≤200 tokens of state per branch").

**Acceptance:** instrumented run report includes per-stage context sizes (`report.json` gains
`context_tokens_per_stage`); a test asserts the adversary/judge prompts contain no branch
payloads; N=3 real-task run shows orchestrator peak < 20k.

### 4.2 Cut the always-on session tax

1. **Description budget.** ~59 skill descriptions (~1,650 tokens) + 34 agent descriptions
   (~1,430 tokens) ≈ **3,000 tokens injected into every session**, mostly for stubs (§6 trims
   the count; this item caps the survivors). Policy: descriptions ≤ 15 words; CI check in
   `generate_components.py`'s successor. Target < 1,000 tokens total.
2. **research_gate must earn its 110 tokens.** Today it fires on nearly every coding prompt
   (`build|create|write|add|fix|...` are unavoidable words) and repeats the full protocol every
   time. Changes: (a) fire **once per session** (state file under `.pqa/`), then go silent;
   (b) require a complexity heuristic (e.g., ≥ 2 sentences or ≥ 15 words) so "fix typo" doesn't
   trigger a multi-branch protocol pitch; (c) shrink the injected text to two lines pointing at
   `/pqa`; (d) honor an env kill-switch.
3. **Hook kill-switch parity with ECC.** Add `PQA_DISABLED_HOOKS=research_gate,verify_loop`
   (comma list) and a `[hooks]` block in `pqa-config.toml`. Every blocking hook's error message
   states its disable path — ECC's gateguard does this and it's the right DX even when the
   answer is "don't disable security_gate".
4. **Stop making 26 agents read root `CLAUDE.md`.** Every stub agent's first instruction loads
   a ~1,000-word file into its context to learn a loop it participates in for one narrow step.
   Replace with a 60-token "loop contract" block inlined by the generator into each agent.

### 4.3 Memory that retrieves by relevance, not recency

`pqa/memory.py:recent_failures()` returns the last 10 failures by timestamp and is the entire
retrieval story (and the orchestrator never even calls it — only the frame-loader is *told* to).
World-class:

1. Add SQLite **FTS5** virtual tables over `precipitates` and `failures` (stdlib-compatible,
   no deps — fits the build constraints). Frame-loader queries top-k by task keywords.
2. Hard injection budget: ≤ 400 tokens of prior-art context at frame-load, ranked, with IDs so
   the run report can cite which memories actually influenced the run.
3. Make the orchestrator's frame step actually perform the query (it's currently aspirational).

**Acceptance:** a seeded-memory test shows a task retrieving the relevant failure (not the most
recent); run report lists `memories_injected: [ids]`.

### 4.4 Bound the recursion

`pqa-spiral-coordinator` can re-enter the full loop with no depth limit; only the (broken)
budget cap brakes it. Add `max_spiral_depth` (default 1) to config, enforced in the engine,
surfaced in the report.

---

## 5. P1 — Efficiency: ECC-parity economics

### 5.1 Model routing (the single biggest cost lever)

All 34 agents pin `model: opus`. The cost-governor agent — which does arithmetic — runs on the
most expensive model in the catalog. Route by job:

| Role | Agents | Model |
|---|---|---|
| Judgment-critical | adversary, collapse-judge, unknown-scout | **opus** (or session-inherit) |
| Generation | generators/branchers | **sonnet** default; opus for the P-reframe branch or when `/tune` says the task warrants it |
| Mechanical execution | verifier, regression-sentinel, baseline-runner, reconciler | **sonnet** |
| Bookkeeping | cost-governor, run-reporter, divergence-auditor, memory-curator, failure-taxonomist, eval-runner | **haiku** |
| Orchestration | orchestrator | **sonnet** (it dispatches and bookkeeps; the engine + judge make the decisions) |

Directionally this cuts ~10 Opus dispatches per run to 2–3, a ~60–75% per-run cost reduction
*before* the context fixes in §4 shrink the prompts themselves. Make routing data-driven later
(`/tune` reading `cost_runs`), but ship the static table now.

### 5.2 Kill branches early, spend on survivors

Order verification by cost: lint/type-check first (seconds, no model), kill compile-broken
branches **before** the adversary sees them. The adversary is the most expensive judgment pass;
it should only attack branches that can possibly win. The engine already has the right
primitives (`score_all`, `survives`) — the orchestrator just runs stages in the wrong order
for cost.

### 5.3 Make `/cost`, `/budget`, `/tune` real

They point at stub agents today. `/cost` and `/budget` should be thin Bash wrappers over the
engine (`cost_runs` table + `CostGovernor`) — no model call at all. `/tune` becomes real once
it reads ≥ 10 rows of `cost_runs` + eval outcomes and proposes config diffs (that's the
`pqa-harness-optimizer` promise; implement or cut).

### 5.4 Run resume

A 10-dispatch loop that dies at dispatch 8 currently restarts from zero — the most expensive
failure mode a harness can have. Journal each stage's completion to `.pqa/state.json`
(stage, artifact paths, spend so far); `/pqa --resume <session_id>` re-enters at the first
incomplete stage. (ECC ships session save/resume; PQA's equivalent is run-level resume —
arguably more valuable because runs are expensive.)

---

## 6. P0/P1 — The surface: depth over breadth

The catalog claims 34 agents / 59 skills / 27 commands, but 26 agents are an identical 27-line
template, all 59 skills are description-only stubs (every body is the same boilerplate; no
playbook content), and 26 of 27 commands are one-line pointers. `scripts/generate_components.py`
manufactures the appearance of an ecosystem. **This is the inverse of world-class: ECC's surface
is large because each skill is a real playbook; PQA's is large because a generator stamped it.**

1. **Invert the generator.** Components are hand-written; the script becomes a *validator*
   (frontmatter schema, description length, count drift vs `docs/catalog.json`) instead of a
   *generator*.
2. **Skills: 59 → ~12, each a real playbook** (the ECC `agent-harness-construction` /
   `python-patterns` depth bar — concrete protocols, worked examples, anti-patterns):
   `superposition-branching`, `adversarial-collision`, `empirical-collapse`,
   `topological-divergence`, `perturbation-operators`, `conviction-signalling`,
   `failure-taxonomy`, `git-worktree-orchestration`, `cost-aware-pipeline`,
   `untrusted-research`, one `*-verification` per supported language (folded into a single
   parametrized skill), `the-spiral`. Delete the rest — their content was always going to live
   in the agents anyway.
3. **Agents: 34 → ~14.** Keep the eight substantive ones (orchestrator, frame-loader,
   generator, adversary, verifier, collapse-judge + scout + reconciler) and *promote to real*
   the six the moat needs (memory-curator, failure-taxonomist, instinct-synthesizer,
   self-reflector, eval-runner, baseline-runner). Fold the six language branchers into
   `pqa-generator` parametrized by a language pack (they differ by ~5 lines today). Delete
   vestigial stubs whose logic lives in the engine (cost-governor-as-agent, divergence-auditor,
   conviction-arbiter, run-reporter — these are Bash one-liners over `pqa/`).
4. **Commands: 27 → ~12.** Merge `/frame`+`/superpose`+`/collapse`+`/precipitate` step-through
   into `/pqa --step`. Keep `/pqa`, `/attack`, `/verify`, `/baseline`, `/eval`, `/memory`,
   `/dashboard`, `/cost`, `/budget`, `/instinct-export`, `/instinct-import`, `/install`.
   Drop the 35-word invariant footer from every command body (it's in CLAUDE.md once).
5. **Fix `pqa-researcher` vs `pqa-frame-loader`.** Two agents claim the research frame; the
   hook points at the stub. Keep frame-loader, delete researcher, update the hook text.

**Acceptance:** validator CI green; session description tax measured < 1,000 tokens; every
surviving skill ≥ 60 lines of real content; every surviving agent independently runnable
(its prompt alone suffices without the orchestrator spoon-feeding context).

---

## 7. P1 — Wire the moat (memory, instincts, self-knowledge)

The three continuous loops are the strategic differentiator and they are currently
ornamental: the `signals` table has **no write path anywhere**, `instincts` is written only by
the import script, `recent_failures` has no caller, and `pqa-self-reflector` would read zero
rows forever.

1. **Signals:** `precipitate_capture.py` already parses `conviction:` lines from subagent
   transcripts — write them to `signals` (branch, conviction, basis, run id). After collapse,
   the engine back-fills outcome (`verified`, `survived`, `won`) per signal.
2. **Calibration:** `pqa-self-reflector` (now real, on haiku/sonnet) reads `signals` joined to
   outcomes and emits the calibration table: P(win | conviction=high) vs P(win | no signal).
   This number is the empirical answer to "do hunches mean anything?" — the most novel data
   PQA can produce. Surface it in `/dashboard`.
3. **Instinct synthesis:** implement the clustering the README promises — group precipitates/
   failures by FTS similarity + domain tag, emit instincts with confidence = support count;
   decay confidence when contradicted. Engine code, not agent vibes.
4. **Close the loop:** frame-loader injects top-k instincts (≤ 400-token budget from §4.3) and
   the run report records which instincts were injected *and whether the winner agreed with
   them* — instinct hit-rate becomes a tracked metric.

**Acceptance:** after 5 demo runs, `/dashboard` shows non-zero signals, ≥ 1 synthesized
instinct, and a calibration row; an E2E test covers transcript → signal → outcome → instinct.

---

## 8. P1 — Prove it (the falsifiability debt)

README: "If PQA doesn't beat single-pass on your work, the harness will show you." Nothing in
the repo has ever shown anything — no published run, no win-rate, no cost-per-task. For a
project whose mission is *evidence over eloquence*, the missing self-evidence is the single
biggest credibility gap.

1. **Benchmark set:** 8–12 small, real tasks (bug fix with hidden edge case, refactor with
   regression trap, API design with a non-obvious constraint…) checked into `evals/`, each with
   a locked verifier.
2. **`/eval` runs PQA vs `/baseline`** on the set; emits win-rate, UNVERIFIED rate, cost ratio,
   and divergence stats into `evals/results/<date>.json`.
3. **Publish in README** — a small honest table, including the losses. Re-run on release.
4. **Auto-baseline cheap mode:** every real `/pqa` run records a haiku/sonnet single-pass
   baseline (one dispatch) so longitudinal win-rate accrues from actual usage, not just the
   benchmark set (`baselines` table + `pqa/baseline.py.compare` already exist — call them).
5. **Examples that show, not tell:** replace two of the three copy-paste `examples/*-CLAUDE.md`
   templates with a recorded real run — task in, branches, findings, collapse decision,
   precipitate out — so a prospective user sees the product before installing.

**Acceptance:** README contains a results table with ≥ 8 tasks and a dated methodology note;
CI runs a 2-task smoke eval nightly.

---

## 9. P2 — Worktree Phase 1 (the headline feature)

The README's status section is honest that branches currently run in-context; `docs/architecture.md`
meanwhile lists worktree parallelization as a present component (fix that — §10). Shipping it:

1. Engine-owned worktree lifecycle (`pqa/worktrees.py`): create N worktrees on `pqa/<run>-bN`
   (the shell scripts become thin callers), with `trap`-equivalent cleanup on partial failure
   and a registry in `.pqa/state.json` so `reconcile` can always find strays.
2. Generators receive `{worktree_path}` and write real code there; the verifier runs the real
   suite *in the worktree* (true isolation — today parallel verifiers in one tree would race).
3. `respawn-pair` (§3.3) becomes meaningful: kill one worktree, respawn one branch.
4. Reconcile: survivor merges `--no-ff` (abort on conflict), losers archived as failure rows
   + deleted; `git worktree prune`; assert clean state.
5. Keep the Phase-0 in-context mode behind `branches_mode = "context" | "worktree"` for
   no-git contexts and cheap runs.

**Acceptance:** N=3 run produces 3 worktrees, parallel verification, clean reconcile with zero
orphans (test simulates a mid-run kill); `git worktree list` clean after every test.

---

## 10. P2 — Docs and DX

1. **Resolve the contradictions** (each misleads a real adopter):
   - Loop is 4 stages in one README line, 5 in the table/CLAUDE.md. Standardize on 5; document
     that `/collapse` performs collide+collapse or split the command.
   - "Five enforcing hooks" vs SECURITY.md's accurate "two blocking, rest fail-open." Use
     SECURITY.md's language everywhere.
   - "95%+ coverage" (README) vs the enforced 80% floor (CONTRIBUTING). State both honestly.
   - architecture.md presents worktrees as shipped; README says next. Mark Phase clearly.
   - "every agent on Opus" — currently true via frontmatter but described as if dispatch-wired;
     after §5.1, document the routing table instead.
2. **Quickstart with a real transcript** — install → `/pqa <real task>` → what you'll see at
   each gate → where artifacts/memory land → what it cost. The current README jumps from
   install to philosophy.
3. **Configuration reference** — every `pqa-config.toml` key and `PQA_*` env var: type, default,
   effect (config.py docstrings are nearly this already; generate the page from them).
4. **Cost expectations table** — tokens and $ for a typical N=3 run at the §5.1 routing, plus
   the knobs that change it. ECC users expect this; budget-blind adoption is how harnesses get
   uninstalled.
5. **Troubleshooting** — all-branches-fail (what you see, what to do), UNVERIFIED results,
   stuck worktrees, memory DB reset, hook disable paths.
6. **Comparison page** — PQA vs plain Claude Code, vs ECC, vs superpowers-style TDD flows:
   when to reach for which. Positioning PQA as *complementary to ECC* (method vs toolbox) is
   both true and disarming.

---

## 11. ECC parity checklist (adopt / skip)

What "as efficient as ECC" concretely means here:

**Adopt:**
- [ ] Hook kill-switches + disable-path-in-error-message (`ECC_DISABLED_HOOKS` pattern) — §4.2
- [ ] Model routing by job tier (ECC `model-route` philosophy) — §5.1
- [ ] Cost visibility command backed by real ledger data (ECC `cost-report`) — §5.3
- [ ] Deep playbook skills, few rather than many — §6
- [ ] Session/run resume — §5.4
- [ ] Project-scoped learning with confidence decay (ECC continuous-learning-v2's lesson:
      unscoped instincts contaminate across projects) — §7.3
- [ ] Periodic cost notice during expensive operations (ECC's PostToolUse cost notices), but
      **rate-limited** (see skip list)

**Deliberately skip (ECC's weaknesses, not strengths):**
- 300-component sprawl. PQA's focus *is* the differentiation; §6 goes the other direction.
- Per-prompt ceremony gates (ECC's fact-forcing gate fires before a trivial `gh auth status`).
  PQA's research_gate has the same disease (§4.2) — fix it there, don't add more.
- Unconditional always-on context injection. Every PQA injection stays conditional, capped,
  and once-per-session.

---

## 12. Sequencing

| Phase | Items | Outcome |
|---|---|---|
| **1. Make it true** | §3 (cost model, wiring, defects), §6.1 validator inversion | A default `/pqa` run completes; no silent failures; no self-aborting math |
| **2. Make it lean** | §4 (context redesign, session tax, memory retrieval), §5.1–5.3 (routing, early-kill, real cost cmds) | < 1k session tax; < 20k orchestrator peak; ~60–75% cost cut |
| **3. Make it deep** | §6.2–6.5 (surface trim + real playbooks), §7 (moat wiring) | Every shipped component is real; the three loops produce data |
| **4. Make it proven** | §8 (evals published), §5.4 (resume) | README shows win-rate; runs are resumable |
| **5. Make it parallel** | §9 (worktrees), §10 (docs) | The headline architecture ships; docs match reality |

---

## 13. Acceptance scorecard (the definition of world-class)

Track these in `/dashboard`; a release is world-class when all are green:

| Metric | Today | Target |
|---|---|---|
| Default `/pqa` run completes within default budget | ❌ (self-aborts) | ✅ |
| Fixed per-session context tax (descriptions + hooks) | ~3,100 tokens | < 1,000 |
| Orchestrator peak context, N=3 real task | ~30–80k (unbounded) | < 20k, instrumented |
| Opus dispatches per N=3 run | ~10 + orchestrator | ≤ 3 |
| Stub components shipped | 85+ (26 agents, 59 skills) | 0 |
| `signals` rows after 5 runs | 0 (no write path) | > 0, with calibration table |
| Published PQA-vs-baseline results | none | README table, ≥ 8 tasks, refreshed per release |
| Run resume after interrupt | restart from zero | resumes at last completed stage |
| Worktree isolation | not implemented | N worktrees, zero orphans under failure injection |
| Hook escape hatches documented | none | every hook; stated in its own error text |

---

*Method note: this review was produced by a Fable 5 pass over the full repo (engine read
end-to-end; plugin surface, hooks, and docs mapped by parallel readers and spot-verified),
with cost/budget math checked against current published model pricing. In PQA's own terms:
the findings above are the adversary pass; the acceptance criteria are the verifier. Collapse
is yours.*
