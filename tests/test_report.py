"""Tests for per-run artefact writing.

A PQA run is only trustworthy if it leaves a paper trail. report.py turns a RunReport
into a structured JSON + human-readable Markdown artefact and (optionally) a row in the
cost_runs telemetry table — together these are what makes a converged solution
inspectable after the fact.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from pqa.baseline import Baseline, Comparison
from pqa.collapse import BranchResult, CollapseOutcome
from pqa.cost import Budget, CostGovernor
from pqa.divergence import BranchSimilarity, DivergenceReport
from pqa.memory import connect
from pqa.orchestrator import RunReport
from pqa.report import RunArtefact, record_cost_run, write_report
from pqa.superposition import Branch


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "m.db")
    yield c
    c.close()


def _branch(branch_id: str = "b0", output: str = "def x(): pass") -> Branch:
    return Branch(id=branch_id, prompt=f"prompt for {branch_id}", output=output)


def _branch_result(name: str = "b0", verified: bool = True) -> BranchResult:
    return BranchResult(
        name=name,
        verified=verified,
        has_tests=True,
        coverage=85.0,
        findings_resolved=2,
        findings_total=3,
        conviction=None,
        incremental=True,
    )


def _divergence_report() -> DivergenceReport:
    return DivergenceReport(
        pair_similarities=[BranchSimilarity(branch_a=0, branch_b=1, similarity=0.4)],
        mean_similarity=0.4,
        max_similarity=0.4,
        min_similarity=0.4,
        most_similar_pair=(0, 1),
        verdict="divergent",
    )


def _run_report(
    survivor: Branch | None = None,
    branches: list[Branch] | None = None,
    aborted: bool = False,
    baseline_comparison: Comparison | None = None,
) -> RunReport:
    branches = branches or [_branch("b0"), _branch("b1", "class Y:\n    pass")]
    branch_results = [_branch_result(b.id, verified=(b.id == "b0")) for b in branches]
    return RunReport(
        task="rate-limiter",
        session_id="demo-1",
        survivor=survivor,
        survivor_result=branch_results[0] if survivor else None,
        collapse=CollapseOutcome(
            survivor=branch_results[0] if survivor else None,
            reason="survived attack and passed tests",
            unverified=False,
            confidence="verified (85% coverage)",
        ),
        divergence=_divergence_report(),
        cost_report="status: ok\nspent: $0.12 of $2.00\nbranches:\n  b0: $0.05\n  b1: $0.05",
        baseline_comparison=baseline_comparison,
        branches=branches,
        branch_results=branch_results,
        aborted=aborted,
        abort_reason="cost exceeded" if aborted else None,
        started_at=1_700_000_000,
        finished_at=1_700_000_120,
    )


# ---------------------------------------------------------------------------
# Artefact directory + files


def test_write_report_creates_session_directory(tmp_path: Path):
    survivor = _branch("b0")
    artefact = write_report(_run_report(survivor=survivor), tmp_path)
    assert artefact.artefact_dir.exists()
    assert artefact.artefact_dir.parent == tmp_path
    assert artefact.json_path.exists()
    assert artefact.markdown_path.exists()


def test_write_report_returns_artefact_dataclass(tmp_path: Path):
    survivor = _branch("b0")
    artefact = write_report(_run_report(survivor=survivor), tmp_path)
    assert isinstance(artefact, RunArtefact)
    assert artefact.json_path.suffix == ".json"
    assert artefact.markdown_path.suffix == ".md"


def test_write_report_writes_per_branch_outputs(tmp_path: Path):
    branches = [_branch("b0", "code-a"), _branch("b1", "code-b")]
    artefact = write_report(_run_report(survivor=branches[0], branches=branches), tmp_path)
    branch_dir = artefact.artefact_dir / "branches"
    assert (branch_dir / "b0.txt").read_text() == "code-a"
    assert (branch_dir / "b1.txt").read_text() == "code-b"


def test_write_report_session_id_used_as_dirname(tmp_path: Path):
    artefact = write_report(_run_report(survivor=_branch("b0")), tmp_path)
    assert artefact.artefact_dir.name == "demo-1"


# ---------------------------------------------------------------------------
# JSON content


def test_json_carries_essential_fields(tmp_path: Path):
    survivor = _branch("b0")
    artefact = write_report(_run_report(survivor=survivor), tmp_path)
    data = json.loads(artefact.json_path.read_text())
    assert data["task"] == "rate-limiter"
    assert data["session_id"] == "demo-1"
    assert data["aborted"] is False
    assert data["survivor"]["id"] == "b0"
    assert "divergence" in data
    assert "cost_report" in data
    assert "branches" in data
    assert "branch_results" in data


def test_json_handles_aborted_run(tmp_path: Path):
    artefact = write_report(_run_report(aborted=True), tmp_path)
    data = json.loads(artefact.json_path.read_text())
    assert data["aborted"] is True
    assert data["abort_reason"] == "cost exceeded"
    assert data["survivor"] is None


def test_json_handles_no_survivor(tmp_path: Path):
    artefact = write_report(_run_report(survivor=None), tmp_path)
    data = json.loads(artefact.json_path.read_text())
    assert data["survivor"] is None


def test_json_includes_baseline_comparison_when_present(tmp_path: Path):
    baseline = Baseline(
        task="rate-limiter",
        response="stub",
        tokens_used=100,
        tests_pass=False,
        coverage=None,
        created_at=1,
    )
    bc = Comparison(
        task="rate-limiter",
        baseline=baseline,
        pqa_response="real code",
        pqa_tokens_used=1000,
        pqa_tests_pass=True,
        pqa_coverage=85.0,
        verdict="pqa_wins",
        rationale="PQA found a solution",
    )
    artefact = write_report(_run_report(survivor=_branch("b0"), baseline_comparison=bc), tmp_path)
    data = json.loads(artefact.json_path.read_text())
    assert data["baseline_comparison"]["verdict"] == "pqa_wins"
    assert data["baseline_comparison"]["pqa_tokens_used"] == 1000


def test_json_is_round_trip_parseable(tmp_path: Path):
    artefact = write_report(_run_report(survivor=_branch("b0")), tmp_path)
    raw = artefact.json_path.read_text()
    parsed = json.loads(raw)
    # Re-serialise; both should yield the same structure.
    assert json.loads(json.dumps(parsed)) == parsed


# ---------------------------------------------------------------------------
# Markdown content


def test_markdown_has_required_sections(tmp_path: Path):
    artefact = write_report(_run_report(survivor=_branch("b0")), tmp_path)
    md = artefact.markdown_path.read_text()
    # Section markers we rely on.
    assert "# PQA Run Report" in md or "# Run report" in md.lower()
    assert "rate-limiter" in md
    assert "demo-1" in md
    assert "b0" in md
    assert "divergent" in md.lower()


def test_markdown_marks_aborted_runs_prominently(tmp_path: Path):
    artefact = write_report(_run_report(aborted=True), tmp_path)
    md = artefact.markdown_path.read_text()
    assert "ABORTED" in md.upper()
    assert "cost exceeded" in md


def test_markdown_includes_cost_report_block(tmp_path: Path):
    artefact = write_report(_run_report(survivor=_branch("b0")), tmp_path)
    md = artefact.markdown_path.read_text()
    assert "status: ok" in md
    assert "$0.12 of $2.00" in md


def test_markdown_lists_each_branch(tmp_path: Path):
    branches = [_branch("b0"), _branch("b1"), _branch("b2")]
    artefact = write_report(_run_report(survivor=branches[0], branches=branches), tmp_path)
    md = artefact.markdown_path.read_text()
    assert "b0" in md
    assert "b1" in md
    assert "b2" in md


# ---------------------------------------------------------------------------
# record_cost_run (cost_runs table integration)


def test_record_cost_run_persists_row(conn: sqlite3.Connection):
    gov = CostGovernor(Budget(max_usd=5.0))
    gov.record("b0", "claude-sonnet-4-6", 1_000, 500)
    gov.record("b1", "claude-sonnet-4-6", 1_000, 500)
    row_id = record_cost_run(conn, session_id="s", task="t", governor=gov, budget_usd=5.0)
    assert row_id > 0
    row = conn.execute(
        "SELECT session_id, task, total_cost, budget_usd, status, branches FROM cost_runs"
    ).fetchone()
    assert row[0] == "s"
    assert row[1] == "t"
    assert row[2] > 0
    assert row[3] == 5.0
    assert row[4] in {"ok", "warn", "abort"}
    assert row[5] == 2


def test_record_cost_run_with_zero_branches(conn: sqlite3.Connection):
    gov = CostGovernor(Budget(max_usd=5.0))
    row_id = record_cost_run(conn, session_id="s", task=None, governor=gov, budget_usd=5.0)
    row = conn.execute("SELECT branches FROM cost_runs WHERE id = ?", (row_id,)).fetchone()
    assert row[0] == 0


# ---------------------------------------------------------------------------
# Existing directory handling


def test_write_report_overwrites_existing_files(tmp_path: Path):
    # First write
    survivor = _branch("b0")
    artefact1 = write_report(_run_report(survivor=survivor), tmp_path)
    # Mutate output, write again
    branches2 = [_branch("b0", "different code"), _branch("b1", "also different")]
    artefact2 = write_report(_run_report(survivor=branches2[0], branches=branches2), tmp_path)
    assert artefact1.json_path == artefact2.json_path
    assert (artefact2.artefact_dir / "branches" / "b0.txt").read_text() == "different code"
