-- PQA memory schema. Persistent across sessions. Stdlib sqlite3.
-- Initialise with:  sqlite3 .claude/memory/pqa_memory.db < .claude/memory/schema.sql

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
    conviction    TEXT,               -- high/medium/low/none — flags instinct-vs-reality divergence
    created_at    INTEGER NOT NULL
);

-- Conviction / "wormhole" signals captured from generators. Instinct telemetry.
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    level       TEXT    NOT NULL,     -- high/medium/low
    basis       TEXT    NOT NULL,     -- the stated non-obvious basis
    survived    INTEGER,              -- 1 if the flagged branch passed verification, 0 if not, NULL unknown
    created_at  INTEGER NOT NULL
);

-- Sigma/frame registry: research-frame vs self-eval-frame disagreements per task.
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
    statement     TEXT    NOT NULL,   -- the learned heuristic, in one line
    confidence    REAL    NOT NULL,   -- 0..1, from supporting evidence
    evidence_n    INTEGER NOT NULL DEFAULT 0,
    origin        TEXT    DEFAULT 'local',  -- 'local' or an import source tag
    created_at    INTEGER NOT NULL,
    UNIQUE(name)
);
CREATE INDEX IF NOT EXISTS idx_instincts_conf ON instincts(confidence DESC);
