-- PQA memory schema, migration 001 — the initial schema.
--
-- Future schema changes go in 002_*.sql, 003_*.sql, etc. The migration runner
-- (pqa.migrations) applies these in order exactly once, tracked via the
-- schema_version table.

-- Named precipitates: the winning insight from a run and why it won.
CREATE TABLE IF NOT EXISTS precipitates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    task        TEXT,                 -- the task this precipitated from
    name        TEXT    NOT NULL,     -- the crystallised name (P_name)
    rationale   TEXT    NOT NULL,     -- why this branch won
    domain      TEXT,                 -- optional vertical/domain tag for moat-building
    created_at  INTEGER NOT NULL
);

-- Failure taxonomy: every dead branch and why it died. The continuous-learning asset.
CREATE TABLE IF NOT EXISTS failures (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,
    task          TEXT,
    approach      TEXT    NOT NULL,   -- the topology that was tried
    death_reason  TEXT    NOT NULL,   -- adversary finding or test failure that killed it
    conviction    TEXT,               -- high/medium/low/none — instinct-vs-reality divergence
    created_at    INTEGER NOT NULL
);

-- Conviction / "wormhole" signals captured from generators. Instinct telemetry.
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    level       TEXT    NOT NULL,     -- high/medium/low
    basis       TEXT    NOT NULL,     -- the stated non-obvious basis
    survived    INTEGER,              -- 1 if the flagged branch passed verification, 0 if not
    created_at  INTEGER NOT NULL
);

-- Frame registry: research-frame vs self-eval-frame disagreements per task.
-- These are the branching axes; reused to avoid re-litigating settled collisions.
CREATE TABLE IF NOT EXISTS frames (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,
    task          TEXT,
    research_view TEXT,
    selfeval_view TEXT,
    disagreement  TEXT,               -- the named gap that became a branching axis
    resolved_by   TEXT,               -- which view the verifier ultimately favoured
    created_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_precip_domain ON precipitates(domain);
CREATE INDEX IF NOT EXISTS idx_failures_approach ON failures(approach);
CREATE INDEX IF NOT EXISTS idx_signals_level ON signals(level);

-- Synthesized instincts: clustered precipitates/failures with a confidence score.
-- Exportable/importable so learning is portable across people, not just sessions.
CREATE TABLE IF NOT EXISTS instincts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    statement     TEXT    NOT NULL,
    confidence    REAL    NOT NULL,
    evidence_n    INTEGER NOT NULL DEFAULT 0,
    origin        TEXT    DEFAULT 'local',
    created_at    INTEGER NOT NULL,
    UNIQUE(name)
);
CREATE INDEX IF NOT EXISTS idx_instincts_conf ON instincts(confidence DESC);

-- Single-pass baselines: the first-attempt solution for each task, used as the
-- side-by-side measurement for PQA's converged answer.
CREATE TABLE IF NOT EXISTS baselines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task          TEXT    NOT NULL,
    response      TEXT    NOT NULL,
    tokens_used   INTEGER NOT NULL,
    tests_pass    INTEGER NOT NULL,
    coverage      REAL,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baselines_task ON baselines(task, created_at DESC);

-- Per-run cost telemetry: a snapshot of cost-governor state at run end.
CREATE TABLE IF NOT EXISTS cost_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,
    task          TEXT,
    total_cost    REAL    NOT NULL,
    budget_usd    REAL    NOT NULL,
    status        TEXT    NOT NULL,
    branches      INTEGER NOT NULL,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cost_runs_session ON cost_runs(session_id);
