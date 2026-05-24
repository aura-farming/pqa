"""Tests for the baseline comparator: records a single-pass first attempt per task and
scores PQA's converged solution against it.

The headline success criterion of PQA is *beats the single-pass baseline*. Without storing
and comparing the baseline, that claim is unmeasurable. This module makes it measurable.
"""

import sqlite3
from pathlib import Path

import pytest

from pqa.baseline import (
    Baseline,
    Comparison,
    compare,
    get_baseline,
    record_baseline,
)
from pqa.memory import connect


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "m.db")
    yield c
    c.close()


def test_connect_creates_baselines_table(conn: sqlite3.Connection):
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "baselines" in tables


def test_record_baseline_returns_object_with_created_at(conn: sqlite3.Connection):
    b = record_baseline(
        conn,
        task="rate-limiter",
        response="def limit(x): return x",
        tokens_used=500,
        tests_pass=True,
        coverage=82.0,
    )
    assert isinstance(b, Baseline)
    assert b.task == "rate-limiter"
    assert b.tokens_used == 500
    assert b.tests_pass is True
    assert b.coverage == 82.0
    assert b.created_at > 0


def test_record_baseline_persists_row(conn: sqlite3.Connection):
    record_baseline(conn, "t", "code", 100, True, 90.0)
    row = conn.execute(
        "SELECT task, response, tokens_used, tests_pass, coverage FROM baselines"
    ).fetchone()
    assert row == ("t", "code", 100, 1, 90.0)


def test_get_baseline_returns_none_for_missing(conn: sqlite3.Connection):
    assert get_baseline(conn, "never-recorded") is None


def test_get_baseline_returns_latest_for_task(conn: sqlite3.Connection):
    record_baseline(conn, "t", "first-attempt", 100, False, None)
    record_baseline(conn, "t", "second-attempt", 200, True, 80.0)
    latest = get_baseline(conn, "t")
    assert latest is not None
    assert latest.response == "second-attempt"
    assert latest.tests_pass is True


def test_record_baseline_rejects_empty_task(conn: sqlite3.Connection):
    with pytest.raises(ValueError):
        record_baseline(conn, "", "code", 100, True)


def test_record_baseline_rejects_negative_tokens(conn: sqlite3.Connection):
    with pytest.raises(ValueError):
        record_baseline(conn, "t", "code", -1, True)


def test_record_baseline_allows_coverage_none(conn: sqlite3.Connection):
    b = record_baseline(conn, "t", "code", 100, True, coverage=None)
    assert b.coverage is None


def _bl(**overrides) -> Baseline:
    defaults = {
        "task": "t",
        "response": "def x(): pass",
        "tokens_used": 100,
        "tests_pass": True,
        "coverage": 80.0,
        "created_at": 1,
    }
    defaults.update(overrides)
    return Baseline(**defaults)


def test_compare_both_fail_baseline_wins():
    baseline = _bl(tests_pass=False)
    c = compare(baseline, "totally different code", pqa_tokens_used=500, pqa_tests_pass=False)
    assert c.verdict == "baseline_wins"
    assert "both fail" in c.rationale.lower() or "neither" in c.rationale.lower()


def test_compare_only_pqa_passes_pqa_wins():
    baseline = _bl(tests_pass=False)
    c = compare(
        baseline,
        pqa_response="different solution",
        pqa_tokens_used=500,
        pqa_tests_pass=True,
    )
    assert c.verdict == "pqa_wins"


def test_compare_only_baseline_passes_baseline_wins():
    baseline = _bl(tests_pass=True)
    c = compare(
        baseline,
        pqa_response="different but broken",
        pqa_tokens_used=500,
        pqa_tests_pass=False,
    )
    assert c.verdict == "baseline_wins"
    assert "regression" in c.rationale.lower() or "broke" in c.rationale.lower()


def test_compare_identical_responses_is_tie():
    baseline = _bl(response="def add(a, b): return a + b", tests_pass=True)
    c = compare(
        baseline,
        pqa_response="def add(a, b): return a + b",
        pqa_tokens_used=500,
        pqa_tests_pass=True,
    )
    assert c.verdict == "tie"
    assert "identical" in c.rationale.lower() or "same" in c.rationale.lower()


def test_compare_both_pass_with_different_response_is_pqa_win():
    baseline = _bl(response="def add(a, b): return a + b", tests_pass=True)
    c = compare(
        baseline,
        pqa_response=(
            "from functools import reduce\n"
            "def add(*args): return reduce(lambda x, y: x + y, args, 0)"
        ),
        pqa_tokens_used=500,
        pqa_tests_pass=True,
    )
    assert c.verdict == "pqa_wins"
    assert "different" in c.rationale.lower() or "non-obvious" in c.rationale.lower()


def test_compare_near_identical_response_is_tie():
    # Same algorithm, trivially-different whitespace/naming.
    baseline = _bl(response="def add(a, b):\n    return a + b\n", tests_pass=True)
    c = compare(
        baseline,
        pqa_response="def add(a, b):\n    return a+b\n",
        pqa_tokens_used=500,
        pqa_tests_pass=True,
    )
    assert c.verdict == "tie"


def test_compare_tracks_token_delta():
    baseline = _bl(tokens_used=100, tests_pass=True)
    c = compare(
        baseline,
        pqa_response="alternative",
        pqa_tokens_used=600,
        pqa_tests_pass=True,
    )
    assert c.pqa_tokens_used == 600
    assert c.baseline.tokens_used == 100


def test_comparison_is_immutable():
    baseline = _bl()
    c = compare(baseline, "x", 1, True)
    with pytest.raises((AttributeError, TypeError)):
        c.verdict = "tie"  # type: ignore[misc]


def test_baseline_is_immutable():
    b = _bl()
    with pytest.raises((AttributeError, TypeError)):
        b.response = "changed"  # type: ignore[misc]


def test_compare_returns_comparison_with_all_fields():
    baseline = _bl()
    c = compare(baseline, "alt", 200, True)
    assert isinstance(c, Comparison)
    assert c.task == baseline.task
    assert c.baseline is baseline
    assert c.pqa_response == "alt"
    assert c.pqa_tokens_used == 200
    assert c.pqa_tests_pass is True
    assert c.verdict in {"pqa_wins", "baseline_wins", "tie"}
    assert c.rationale  # non-empty
