"""Tests for the memory persistence layer."""

import sqlite3
from pathlib import Path

import pytest

from pqa.memory import Failure, connect, recent_failures, record_failure, record_precipitate


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
