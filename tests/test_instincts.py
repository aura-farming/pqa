"""Tests for instinct synthesis and conviction calibration (roadmap §7, Phase 3c).

The moat is three loops: signals → outcomes (calibration), precipitates/failures →
instincts (synthesis), instincts → frames (injection). These tests drive the engine
side of all three; the E2E test at the bottom chains transcript → signal → outcome →
instinct → injection → dashboard, which is roadmap §7's acceptance.
"""

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from pqa.instincts import agrees, calibration, synthesize_instincts
from pqa.memory import (
    Failure,
    backfill_signal_outcomes,
    connect,
    prior_art,
    record_failure,
    record_precipitate,
    record_signal,
    update_signal_outcome,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "m.db")
    yield c
    c.close()


def _seed_backpressure_cluster(conn: sqlite3.Connection) -> None:
    record_precipitate(
        conn,
        "s1",
        "rate limit the ingest API",
        "backpressure beats rejection",
        "bounded queue with backpressure absorbs ingest bursts",
        domain="ratelimiting",
    )
    record_precipitate(
        conn,
        "s2",
        "throttle webhook fan-out",
        "backpressure queue wins again",
        "queue backpressure absorbs bursts better than rejection",
        domain="ratelimiting",
    )


# ---------------------------------------------------------------------------
# Synthesis: precipitates/failures → instincts


def test_synthesize_clusters_similar_precipitates(conn: sqlite3.Connection):
    _seed_backpressure_cluster(conn)
    record_precipitate(
        conn,
        "s3",
        "nightly export",
        "delta export",
        "export only the delta and backfill on demand",
        domain="exports",
    )
    instincts = synthesize_instincts(conn)
    assert len(instincts) == 1, "only the 2-strong cluster reaches min_support"
    inst = instincts[0]
    assert inst.name == "backpressure beats rejection"  # earliest precipitate names it
    assert inst.evidence_n == 2
    assert inst.confidence == 0.5  # support / (support + 2), no contradictions
    row = conn.execute(
        "SELECT statement, origin FROM instincts WHERE name=?", (inst.name,)
    ).fetchone()
    assert row is not None
    assert row[1] == "local"


def test_confidence_decays_when_contradicted(conn: sqlite3.Connection):
    _seed_backpressure_cluster(conn)
    record_failure(
        conn,
        "s4",
        "rate limit the ingest API",
        Failure("backpressure queue", "verifier: queue backpressure dropped bursts on the floor"),
    )
    (inst,) = synthesize_instincts(conn)
    assert inst.confidence == 0.35  # 0.5 * 0.7 for one contradiction


def test_budget_deaths_never_contradict(conn: sqlite3.Connection):
    _seed_backpressure_cluster(conn)
    record_failure(
        conn,
        "s4",
        "rate limit the ingest API",
        Failure(
            "backpressure queue", "budget: aborted before judging the backpressure queue bursts"
        ),
    )
    (inst,) = synthesize_instincts(conn)
    assert inst.confidence == 0.5  # a budget death is not evidence against the approach


def test_min_support_gate(conn: sqlite3.Connection):
    _seed_backpressure_cluster(conn)
    assert synthesize_instincts(conn, min_support=3) == []


def test_synthesis_never_clobbers_imported_instincts(conn: sqlite3.Connection):
    _seed_backpressure_cluster(conn)
    conn.execute(
        "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
        "VALUES(?,?,?,?,?,0)",
        ("backpressure beats rejection", "imported wisdom", 0.9, 7, "import:teammate"),
    )
    conn.commit()
    synthesize_instincts(conn)
    stmt, conf, origin = conn.execute(
        "SELECT statement, confidence, origin FROM instincts WHERE name=?",
        ("backpressure beats rejection",),
    ).fetchone()
    assert (stmt, conf, origin) == ("imported wisdom", 0.9, "import:teammate")


def test_resynthesis_updates_the_local_row(conn: sqlite3.Connection):
    _seed_backpressure_cluster(conn)
    synthesize_instincts(conn)
    record_precipitate(
        conn,
        "s5",
        "ingest surge protection",
        "backpressure again",
        "backpressure queue absorbs bursts, rejection loses data",
        domain="ratelimiting",
    )
    (inst,) = synthesize_instincts(conn)
    assert inst.evidence_n == 3
    assert conn.execute("SELECT count(*) FROM instincts").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Calibration: signals joined to outcomes


def test_calibration_rows(conn: sqlite3.Connection):
    s1 = record_signal(conn, "r1", "high", "queue absorbs bursts", branch="b1")
    update_signal_outcome(conn, s1, survived=True, verified=True, won=True)
    s2 = record_signal(conn, "r2", "high", "lock-free is safe here", branch="b0")
    update_signal_outcome(conn, s2, survived=True, verified=False, won=False)
    record_signal(conn, "r3", "medium", "hunch", branch="b2")  # no outcome yet
    record_precipitate(conn, "r1", "t", "winner", "why")
    record_failure(conn, "r1", "t", Failure("loser-a", "verifier: failed"))
    record_failure(conn, "r2", "t", Failure("loser-b", "budget: aborted at collide"))

    rows = {r.level: r for r in calibration(conn)}
    assert rows["high"].n == 2
    assert rows["high"].wins == 1
    assert rows["high"].p_win == 0.5
    assert rows["high"].pending == 0
    assert rows["medium"].n == 0
    assert rows["medium"].pending == 1
    base = rows["base"]
    assert base.n == 2, "budget deaths are excluded from the base denominator"
    assert base.wins == 1
    assert base.p_win == 0.5


def test_agrees_is_a_token_overlap_heuristic():
    statement = "bounded queue with backpressure absorbs ingest bursts"
    assert agrees(statement, "implemented a backpressure queue rejecting at the producer")
    assert not agrees("delta export backfill on demand", "token bucket counter per tenant")


# ---------------------------------------------------------------------------
# E2E: transcript → signal → outcome → instinct → injection → dashboard


def _load_dashboard():
    spec = importlib.util.spec_from_file_location(
        "dashboard", REPO_ROOT / "scripts" / "dashboard.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2e_transcript_to_signal_to_outcome_to_instinct(tmp_path: Path):
    """Roadmap §7 acceptance: the three loops produce data end to end."""
    db = tmp_path / ".claude" / "hooks" / "memory" / "pqa_memory.db"
    conn = connect(db)  # current schema, incl. signal outcome columns

    # 1. transcript → signal (the SubagentStop capture hook, run for real)
    digest = (
        '{"branch_id": "b1", "topology_axis": "pull-based backpressure queue"} '
        "conviction: high, basis: queue backpressure absorbs ingest bursts"
    )
    transcript = tmp_path / ".claude" / "t.jsonl"
    transcript.write_text(json.dumps({"message": {"role": "assistant", "content": digest}}) + "\n")
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "hooks" / "precipitate_capture.py")],
        input=json.dumps(
            {"cwd": str(tmp_path), "session_id": "e2e", "transcript_path": str(transcript)}
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    level, branch, outcome_at = conn.execute(
        "SELECT level, branch, outcome_at FROM signals WHERE session_id='e2e'"
    ).fetchone()
    assert (level, branch, outcome_at) == ("high", "b1", None)

    # 2. signal → outcome (the back-fill the orchestrator runs post-collapse)
    assert (
        backfill_signal_outcomes(conn, "e2e", branch="b1", survived=True, verified=True, won=True)
        == 1
    )

    # 3. precipitates → instinct
    _seed_backpressure_cluster(conn)
    assert synthesize_instincts(conn)

    # 4. instinct → next frame, cited
    art = prior_art(conn, "throttle the ingest API under burst load")
    assert any(i.startswith("instinct:") for i in art.ids)
    assert "[instinct:" in art.text

    # 5. the dashboard surfaces calibration + instincts
    rendered = _load_dashboard().render(db)
    assert "calibration" in rendered.lower()
    assert "instinct" in rendered.lower()
    conn.close()
