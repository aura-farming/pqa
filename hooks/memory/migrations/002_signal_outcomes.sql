-- PQA memory schema, migration 002 — conviction-signal outcome columns.
--
-- Signals are captured live (by hooks/precipitate_capture.py and the engine) the
-- moment a generator flags conviction; outcomes only exist after collapse. These
-- columns let the engine back-fill what actually happened to the flagged branch,
-- which is the raw material for the calibration table P(win | conviction).
--
--   branch     — which branch the signal was attached to (b0, b1, ...)
--   verified   — 1 if that branch passed the verifier, 0 if not
--   won        — 1 if that branch was the collapse survivor, 0 if not
--   outcome_at — when the back-fill happened (epoch seconds)
--
-- (`survived` — survived the adversary collision — already exists from 001.)
--
-- FTS5 search indexes are deliberately NOT created here: migrations must apply on
-- every SQLite build, including ones compiled without FTS5. pqa.memory creates the
-- index tables conditionally at connect() time and falls back to LIKE search.

ALTER TABLE signals ADD COLUMN branch TEXT;
ALTER TABLE signals ADD COLUMN verified INTEGER;
ALTER TABLE signals ADD COLUMN won INTEGER;
ALTER TABLE signals ADD COLUMN outcome_at INTEGER;

CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session_id);
