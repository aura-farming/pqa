"""Tests for the memory persistence layer."""

import sqlite3
from pathlib import Path

import pytest

from pqa.cost import estimate_tokens
from pqa.memory import (
    Failure,
    PriorArt,
    backfill_signal_outcomes,
    connect,
    fts5_available,
    prior_art,
    recent_failures,
    record_failure,
    record_precipitate,
    record_signal,
    search_failures,
    search_instincts,
    search_precipitates,
    update_signal_outcome,
)


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "m.db")  # auto-inits from schema.sql
    yield c
    c.close()


def test_connect_creates_schema(conn: sqlite3.Connection):
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"precipitates", "failures", "signals", "frames"} <= tables


def test_record_and_read_precipitate(conn: sqlite3.Connection):
    record_precipitate(
        conn, "s1", "rate limiter", "token-bucket-stream", "beat the queue on bursts"
    )
    row = conn.execute("SELECT name, rationale FROM precipitates").fetchone()
    assert row == ("token-bucket-stream", "beat the queue on bursts")


def test_recent_failures_returns_newest_first(conn: sqlite3.Connection):
    record_failure(conn, "s1", "t", Failure("fixed-window", "fails burst-at-boundary", "high"))
    record_failure(conn, "s1", "t", Failure("global-lock", "serialises throughput"))
    out = recent_failures(conn, limit=5)
    assert out[0][0] == "global-lock"  # most recent first
    assert out[1][0] == "fixed-window"


def test_recent_failures_respects_limit(conn: sqlite3.Connection):
    for i in range(5):
        record_failure(conn, "s1", "t", Failure(f"approach-{i}", "died"))
    assert len(recent_failures(conn, limit=3)) == 3


def test_failure_default_conviction_is_none(conn: sqlite3.Connection):
    record_failure(conn, "s1", "t", Failure("x", "y"))
    assert conn.execute("SELECT conviction FROM failures").fetchone()[0] == "none"


# ---------------------------------------------------------------------------
# Conviction-signal write path (roadmap §7 — the moat finally gets writers)


def test_record_signal_returns_id_and_persists_row(conn: sqlite3.Connection):
    sid = record_signal(conn, "s1", "high", "burst pattern matches a prior incident", branch="b2")
    row = conn.execute(
        "SELECT id, session_id, level, basis, branch, survived, verified, won FROM signals"
    ).fetchone()
    assert row == (
        sid,
        "s1",
        "high",
        "burst pattern matches a prior incident",
        "b2",
        None,
        None,
        None,
    )


def test_record_signal_branch_is_optional(conn: sqlite3.Connection):
    record_signal(conn, "s1", "low", "weak hunch")
    assert conn.execute("SELECT branch FROM signals").fetchone()[0] is None


def test_record_signal_rejects_unknown_level(conn: sqlite3.Connection):
    with pytest.raises(ValueError, match="level"):
        record_signal(conn, "s1", "extreme", "overconfident")


def test_update_signal_outcome_backfills_and_stamps(conn: sqlite3.Connection):
    sid = record_signal(conn, "s1", "high", "gut", branch="b1")
    assert update_signal_outcome(conn, sid, survived=True, verified=True, won=False) is True
    row = conn.execute(
        "SELECT survived, verified, won, outcome_at FROM signals WHERE id=?", (sid,)
    ).fetchone()
    assert row[0:3] == (1, 1, 0)
    assert row[3] is not None and row[3] > 0


def test_update_signal_outcome_unknown_id_returns_false(conn: sqlite3.Connection):
    assert update_signal_outcome(conn, 999, won=False) is False


def test_update_signal_outcome_requires_at_least_one_outcome(conn: sqlite3.Connection):
    sid = record_signal(conn, "s1", "medium", "gut")
    with pytest.raises(ValueError, match="outcome"):
        update_signal_outcome(conn, sid)


def test_update_signal_outcome_partial_leaves_others_null(conn: sqlite3.Connection):
    sid = record_signal(conn, "s1", "high", "gut")
    update_signal_outcome(conn, sid, won=True)
    row = conn.execute("SELECT survived, verified, won FROM signals WHERE id=?", (sid,)).fetchone()
    assert row == (None, None, 1)


# ---------------------------------------------------------------------------
# Relevance search (roadmap §4.3 — retrieve by relevance, not recency)


def _seed_failures(conn: sqlite3.Connection) -> None:
    # The rate-limiter failure is deliberately the OLDEST row: recency-based
    # retrieval would never surface it first.
    record_failure(
        conn,
        "s1",
        "build a rate limiter",
        Failure("fixed-window counter", "fails burst-at-boundary", "high"),
    )
    record_failure(
        conn, "s2", "style the marketing site", Failure("css-grid-everywhere", "broke safari")
    )
    record_failure(conn, "s3", "ship the newsletter", Failure("inline-styles", "clipped in gmail"))


def test_search_failures_ranks_relevance_over_recency(conn: sqlite3.Connection):
    _seed_failures(conn)
    hits = search_failures(conn, "rate limiter burst handling")
    assert hits, "expected at least one hit"
    assert hits[0].approach == "fixed-window counter"


def test_search_failures_hit_carries_row_identity(conn: sqlite3.Connection):
    _seed_failures(conn)
    hit = search_failures(conn, "rate limiter burst")[0]
    assert hit.id >= 1
    assert hit.death_reason == "fails burst-at-boundary"
    assert hit.task == "build a rate limiter"


def test_search_precipitates_ranks_relevance_over_recency(conn: sqlite3.Connection):
    record_precipitate(
        conn,
        "s1",
        "build a rate limiter",
        "token-bucket-stream",
        "absorbed bursts the queue dropped",
    )
    record_precipitate(conn, "s2", "style the site", "grid-areas", "named areas beat nesting")
    hits = search_precipitates(conn, "rate limiter bursts")
    assert hits and hits[0].name == "token-bucket-stream"


def test_search_returns_empty_for_blank_query(conn: sqlite3.Connection):
    _seed_failures(conn)
    assert search_failures(conn, "   ") == []
    assert search_precipitates(conn, "") == []


def test_search_returns_empty_when_nothing_matches(conn: sqlite3.Connection):
    _seed_failures(conn)
    assert search_failures(conn, "quantum chromodynamics") == []


def test_search_is_safe_against_fts_query_syntax(conn: sqlite3.Connection):
    _seed_failures(conn)
    # None of these may raise, whatever the backend (FTS5 MATCH grammar or LIKE).
    for hostile in ['"unbalanced', "NEAR(", "a AND OR NOT b", "col:value", "*", "-"]:
        search_failures(conn, hostile)
        search_precipitates(conn, hostile)


def test_search_respects_limit(conn: sqlite3.Connection):
    for i in range(8):
        record_failure(conn, "s", "t", Failure(f"rate limiter v{i}", "died"))
    assert len(search_failures(conn, "rate limiter", limit=3)) == 3


def test_search_falls_back_to_like_without_fts5(tmp_path: Path, monkeypatch):
    """On SQLite builds compiled without FTS5 the index is never created and
    search degrades to LIKE scoring — same relevance contract, no crash."""
    monkeypatch.setattr("pqa.memory.fts5_available", lambda _conn: False)
    c = connect(tmp_path / "nofts.db")
    try:
        fts_tables = c.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_fts'").fetchall()
        assert fts_tables == []  # proves we exercise the fallback path
        _seed_failures(c)
        hits = search_failures(c, "rate limiter burst handling")
        assert hits and hits[0].approach == "fixed-window counter"
    finally:
        c.close()


def test_connect_rebuilds_fts_index_after_foreign_writes(tmp_path: Path):
    """Rows inserted by a writer without FTS5 (e.g. a stdlib hook on another
    build) get picked up by the drift rebuild on the next connect()."""
    db = tmp_path / "drift.db"
    c = connect(db)
    if not fts5_available(c):
        c.close()
        pytest.skip("FTS5 not available in this SQLite build")
    c.execute(
        "INSERT INTO failures(session_id, task, approach, death_reason, conviction, created_at)"
        " VALUES('s9','rate limiting','sliding-log','memory blowup','none',1)"
    )
    c.commit()
    c.close()

    c2 = connect(db)
    try:
        hits = search_failures(c2, "sliding log rate limiting")
        assert any(h.approach == "sliding-log" for h in hits)
    finally:
        c2.close()


# ---------------------------------------------------------------------------
# prior_art — the bounded injection block for frame-load (roadmap §4.3.2)


def test_prior_art_empty_db_is_empty(conn: sqlite3.Connection):
    assert prior_art(conn, "anything at all") == PriorArt(ids=(), text="")


def test_prior_art_cites_relevant_memories_with_ids(conn: sqlite3.Connection):
    record_failure(
        conn,
        "s1",
        "build a rate limiter",
        Failure("fixed-window counter", "fails burst-at-boundary", "high"),
    )
    record_precipitate(
        conn,
        "s1",
        "build a rate limiter",
        "token-bucket-stream",
        "absorbed bursts the queue dropped",
    )
    record_failure(conn, "s2", "style the site", Failure("css-grid", "safari broke"))
    art = prior_art(conn, "rate limiter burst handling")
    assert any(i.startswith("failure:") for i in art.ids)
    assert any(i.startswith("precipitate:") for i in art.ids)
    assert "fails burst-at-boundary" in art.text
    assert "token-bucket-stream" in art.text
    for cited in art.ids:  # every cited id appears in the text — auditable injection
        assert f"[{cited}]" in art.text


def test_prior_art_respects_token_budget(conn: sqlite3.Connection):
    for i in range(20):
        record_failure(conn, "s", "rate limiter", Failure(f"rate-limiter-approach-{i}", "x" * 200))
    art = prior_art(conn, "rate limiter", max_tokens=150)
    assert art.ids, "budget admits at least one memory"
    assert len(art.ids) < 5, "budget must cut the candidate list"
    assert estimate_tokens(art.text) <= 150


def test_prior_art_zero_budget_is_empty(conn: sqlite3.Connection):
    record_failure(conn, "s", "rate limiter", Failure("a", "b"))
    assert prior_art(conn, "rate limiter", max_tokens=0) == PriorArt(ids=(), text="")


# ---------------------------------------------------------------------------
# Phase 3c: signal outcome back-fill + instinct retrieval


def test_backfill_signal_outcomes_updates_only_pending(conn: sqlite3.Connection):
    done = record_signal(conn, "s9", "high", "already settled", branch="b0")
    update_signal_outcome(conn, done, won=True)
    record_signal(conn, "s9", "medium", "still open", branch="b1")
    assert backfill_signal_outcomes(conn, "s9", won=False, verified=False) == 1
    assert conn.execute("SELECT won FROM signals WHERE id=?", (done,)).fetchone()[0] == 1
    pending = conn.execute(
        "SELECT count(*) FROM signals WHERE session_id='s9' AND outcome_at IS NULL"
    ).fetchone()[0]
    assert pending == 0


def test_backfill_signal_outcomes_filters_by_branch(conn: sqlite3.Connection):
    record_signal(conn, "s10", "high", "a", branch="b0")
    record_signal(conn, "s10", "high", "b", branch="b1")
    assert backfill_signal_outcomes(conn, "s10", branch="b1", won=True) == 1
    untouched = conn.execute(
        "SELECT outcome_at FROM signals WHERE session_id='s10' AND branch='b0'"
    ).fetchone()[0]
    assert untouched is None


def test_backfill_signal_outcomes_requires_an_outcome(conn: sqlite3.Connection):
    with pytest.raises(ValueError):
        backfill_signal_outcomes(conn, "s11")


def test_search_instincts_ranks_relevance_then_confidence(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
        "VALUES('queue-wins', 'backpressure queue absorbs ingest bursts', 0.6, 3, 'local', 0)"
    )
    conn.execute(
        "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
        "VALUES('also-queues', 'queue ingest with backpressure and absorb bursts', "
        "0.9, 5, 'local', 0)"
    )
    conn.execute(
        "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
        "VALUES('unrelated', 'denormalize the read model', 0.99, 9, 'local', 0)"
    )
    conn.commit()
    hits = search_instincts(conn, "ingest queue backpressure bursts", limit=2)
    assert [h.name for h in hits] == ["also-queues", "queue-wins"]  # relevance tie → confidence
    assert all(h.confidence > 0 for h in hits)


def test_prior_art_cites_instincts_between_failures_and_precipitates(conn: sqlite3.Connection):
    record_failure(conn, "s", "rate limiter", Failure("fixed-window", "verifier: boundary"))
    conn.execute(
        "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
        "VALUES('queue-wins', 'rate limiter queues beat windows', 0.7, 3, 'local', 0)"
    )
    conn.commit()
    record_precipitate(conn, "s", "rate limiter", "queue won", "absorbed the burst")
    art = prior_art(conn, "rate limiter")
    assert any(i.startswith("failure:") for i in art.ids)
    assert any(i.startswith("instinct:") for i in art.ids)
    positions = (
        art.text.index("[failure:"),
        art.text.index("[instinct:"),
        art.text.index("[precipitate:"),
    )
    assert positions == tuple(sorted(positions))
