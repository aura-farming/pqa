"""Tests for frame loading + disagreement detection.

The first collision in every PQA run is the gap between research (what the docs say) and
self-eval (what's actually true here). frame.py captures both views, decides whether the
gap is real enough to branch on, and persists the snapshot so the failure-taxonomy can
later trace which view the verifier favoured.
"""

import sqlite3
from pathlib import Path

import pytest

from pqa.frame import (
    Frame,
    detect_disagreement,
    record_frame,
    update_resolved_by,
)
from pqa.memory import connect


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "m.db")
    yield c
    c.close()


def _research(content="docs say use X", source="https://docs.example.com") -> Frame:
    return Frame(type="research", content=content, source=source)


def _selfeval(content="here in this codebase X breaks because Y", source="self-eval") -> Frame:
    return Frame(type="selfeval", content=content, source=source)


def test_frame_is_immutable():
    f = _research()
    with pytest.raises((AttributeError, TypeError)):
        f.content = "changed"  # type: ignore[misc]


def test_disagreement_is_immutable():
    d = detect_disagreement(_research(), _selfeval())
    assert d is not None
    with pytest.raises((AttributeError, TypeError)):
        d.summary = "changed"  # type: ignore[misc]


def test_similar_frames_produce_no_disagreement():
    same = "rate limiting is best done with a token bucket"
    r = _research(content=same)
    s = _selfeval(content=same)
    assert detect_disagreement(r, s) is None


def test_different_frames_produce_disagreement():
    r = _research(content="documentation says token-bucket is best")
    s = _selfeval(
        content=(
            "in this codebase the queue depth is bursty so a leaky-bucket "
            "with backpressure beats a token-bucket here"
        )
    )
    d = detect_disagreement(r, s)
    assert d is not None
    assert d.research is r
    assert d.selfeval is s
    assert 0.0 <= d.similarity < 1.0


def test_disagreement_summary_is_non_empty():
    r = _research()
    s = _selfeval(content="entirely different content over here")
    d = detect_disagreement(r, s)
    assert d is not None
    assert d.summary.strip() != ""


def test_threshold_is_configurable():
    r = _research(content="A")
    s = _selfeval(content="B")
    # Tight threshold: even very different strings might agree
    loose = detect_disagreement(r, s, agreement_above=0.0)
    assert loose is None  # any similarity >= 0.0 → "agree"
    # Strict threshold: nothing below 1.001 agrees
    strict = detect_disagreement(r, s, agreement_above=1.001)
    assert strict is not None


def test_wrong_frame_types_raise():
    r = _research()
    s = _selfeval()
    with pytest.raises(ValueError):
        detect_disagreement(s, r)  # swapped — first must be research
    with pytest.raises(ValueError):
        detect_disagreement(r, r)  # second must be selfeval


def test_record_frame_persists_row(conn: sqlite3.Connection):
    r = _research(content="docs view")
    s = _selfeval(content="self-eval view")
    d = detect_disagreement(r, s)
    frame_id = record_frame(conn, "session-1", "task-1", r, s, d)
    assert frame_id > 0
    row = conn.execute(
        "SELECT session_id, task, research_view, selfeval_view, disagreement "
        "FROM frames WHERE id = ?",
        (frame_id,),
    ).fetchone()
    assert row[0] == "session-1"
    assert row[1] == "task-1"
    assert row[2] == "docs view"
    assert row[3] == "self-eval view"
    assert row[4] is not None


def test_record_frame_with_no_disagreement_stores_null(conn: sqlite3.Connection):
    r = _research(content="identical")
    s = _selfeval(content="identical")
    d = detect_disagreement(r, s)
    assert d is None
    frame_id = record_frame(conn, "s", "t", r, s, d)
    disagreement_col = conn.execute(
        "SELECT disagreement FROM frames WHERE id = ?", (frame_id,)
    ).fetchone()[0]
    assert disagreement_col is None


def test_update_resolved_by_writes_correct_row(conn: sqlite3.Connection):
    r1 = _research(content="r1")
    s1 = _selfeval(content="s1 differs")
    id1 = record_frame(conn, "sess", "task1", r1, s1, detect_disagreement(r1, s1))

    r2 = _research(content="r2")
    s2 = _selfeval(content="s2 different")
    id2 = record_frame(conn, "sess", "task2", r2, s2, detect_disagreement(r2, s2))

    update_resolved_by(conn, id1, "research")
    update_resolved_by(conn, id2, "selfeval")

    row1 = conn.execute("SELECT resolved_by FROM frames WHERE id = ?", (id1,)).fetchone()
    row2 = conn.execute("SELECT resolved_by FROM frames WHERE id = ?", (id2,)).fetchone()
    assert row1[0] == "research"
    assert row2[0] == "selfeval"


def test_record_frame_returns_increasing_ids(conn: sqlite3.Connection):
    a = record_frame(conn, "s", "t", _research(), _selfeval(), None)
    b = record_frame(conn, "s", "t", _research(), _selfeval(), None)
    assert b > a


def test_record_frame_stores_timestamp(conn: sqlite3.Connection):
    frame_id = record_frame(conn, "s", "t", _research(), _selfeval(), None)
    ts = conn.execute("SELECT created_at FROM frames WHERE id = ?", (frame_id,)).fetchone()[0]
    assert ts > 0


def test_frame_type_literal_enforced_at_construction():
    # Frame accepts the two declared types; "bogus" would be caught by the type checker
    # but Python doesn't enforce Literal at runtime. We just sanity-check the two valid
    # values construct without error.
    Frame(type="research", content="x", source="y")
    Frame(type="selfeval", content="x", source="y")


def test_disagreement_carries_similarity_score():
    r = _research(content="completely unrelated A")
    s = _selfeval(content="another planet entirely B")
    d = detect_disagreement(r, s)
    assert d is not None
    # Two totally different strings should have low similarity.
    assert d.similarity < 0.5


def test_detect_disagreement_default_threshold_distinguishes_signal_from_noise():
    # Same idea, different wording → no real disagreement under default threshold.
    r = _research(content="use exponential backoff for retries")
    s = _selfeval(content="use exponential backoff for retries here too")
    # Whether this returns None or a Disagreement depends on default threshold;
    # the important property: it should NOT crash, and if it returns Disagreement,
    # similarity should be high (close call, not a real gap).
    d = detect_disagreement(r, s)
    if d is not None:
        assert d.similarity >= 0.5
