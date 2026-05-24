"""End-to-end test of the Phase-0 orchestrator.

The orchestrator ties every module together: frame → spawn → generate → divergence →
adversary → verify → collapse → persist → baseline compare. Tests use in-process fakes
for the generator/adversary/verifier callables so the loop can be driven deterministically
without subagent or model calls.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from pqa.baseline import Baseline, record_baseline
from pqa.collapse import BranchResult
from pqa.collision import Finding
from pqa.cost import Budget
from pqa.frame import Frame
from pqa.memory import connect
from pqa.orchestrator import RunReport, VerifyResult, run
from pqa.superposition import Branch

# ---------------------------------------------------------------------------
# Fixtures + fakes


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "m.db")
    yield c
    c.close()


def _research(content="docs say use a token bucket") -> Frame:
    return Frame(type="research", content=content, source="docs")


def _selfeval(content="the queue is bursty so leaky-bucket beats token-bucket here") -> Frame:
    return Frame(type="selfeval", content=content, source="self-eval")


def _make_generator(
    outputs: dict[str, str],
    input_tokens: int = 1000,
    output_tokens: int = 500,
) -> Callable[[Branch], tuple[Branch, int, int]]:
    """Build a fake generator that fills .output from a dict keyed by branch id."""

    def generate(branch: Branch) -> tuple[Branch, int, int]:
        out = outputs.get(branch.id, f"default output for {branch.id}")
        return (
            Branch(
                id=branch.id,
                prompt=branch.prompt,
                output=out,
                conviction=branch.conviction,
                incremental=branch.incremental,
                model=branch.model,
            ),
            input_tokens,
            output_tokens,
        )

    return generate


def _make_adversary(
    findings: list[Finding],
    input_tokens: int = 500,
    output_tokens: int = 300,
) -> Callable[[list[Branch]], tuple[list[Finding], int, int]]:
    def attack(_branches: list[Branch]) -> tuple[list[Finding], int, int]:
        return findings, input_tokens, output_tokens

    return attack


def _make_verifier(
    results: dict[str, VerifyResult],
) -> Callable[[Branch], VerifyResult]:
    def verify(branch: Branch) -> VerifyResult:
        return results.get(branch.id, VerifyResult(has_tests=False, verified=False, coverage=None))

    return verify


def _divergent_outputs() -> dict[str, str]:
    """Two genuinely different topology shapes so divergence verdict is 'divergent'."""
    return {
        "b0": "def add(a, b): return a + b\n",
        "b1": (
            "class Adder:\n"
            "    def __init__(self):\n"
            "        self.history = []\n"
            "    def add(self, *args):\n"
            "        result = sum(args)\n"
            "        self.history.append(result)\n"
            "        return result\n"
        ),
    }


# ---------------------------------------------------------------------------
# Happy path


def test_happy_path_returns_run_report(conn: sqlite3.Connection):
    report = run(
        task="rate-limiter",
        session_id="s1",
        base_prompt="build a rate limiter",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary(
            [
                Finding(
                    branch_id="b0",
                    severity="medium",
                    category="correctness",
                    title="boundary",
                    detail="d",
                    resolved=True,
                ),
            ]
        ),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=85.0),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=40.0),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
        n_branches=2,
    )
    assert isinstance(report, RunReport)
    assert report.task == "rate-limiter"
    assert report.session_id == "s1"
    assert report.aborted is False
    assert len(report.branches) == 2
    assert len(report.branch_results) == 2


def test_survivor_is_the_verified_branch(conn: sqlite3.Connection):
    """b0 passes tests, b1 fails — collapse must pick b0."""
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=80.0),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=None),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.survivor is not None
    assert report.survivor.id == "b0"
    assert report.survivor_result is not None
    assert report.survivor_result.verified is True


# ---------------------------------------------------------------------------
# Cost governance


def test_cost_governor_aborts_when_budget_exceeded(conn: sqlite3.Connection):
    """A tiny budget should abort the run before completion."""
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(
            _divergent_outputs(),
            input_tokens=10_000_000,
            output_tokens=10_000_000,
        ),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=0.01),
        conn=conn,
    )
    assert report.aborted is True
    assert report.abort_reason is not None
    assert "budget" in report.abort_reason.lower() or "cost" in report.abort_reason.lower()


def test_cost_report_includes_branch_breakdown(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert "b0" in report.cost_report
    assert "b1" in report.cost_report


# ---------------------------------------------------------------------------
# Divergence


def test_collapsed_superposition_aborts(conn: sqlite3.Connection):
    """If all branches produce the same output, divergence verdict is 'collapsed' and
    the orchestrator aborts before doing adversary/verify work."""
    identical_outputs = {"b0": "def x(): return 1", "b1": "def x(): return 1"}
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(identical_outputs),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.aborted is True
    assert report.abort_reason is not None
    assert "collapse" in report.abort_reason.lower() or "divergence" in report.abort_reason.lower()


# ---------------------------------------------------------------------------
# All-fail case


def test_all_branches_fail_verification_records_failures(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=False, coverage=None),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=None),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.survivor is None
    # Both branches should be recorded as failures.
    rows = conn.execute("SELECT COUNT(*) FROM failures").fetchone()
    assert rows[0] == 2


# ---------------------------------------------------------------------------
# Persistence


def test_precipitate_recorded_for_survivor(conn: sqlite3.Connection):
    run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=80.0),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=None),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    row = conn.execute("SELECT name FROM precipitates").fetchone()
    assert row is not None
    assert row[0] == "b0"


def test_loser_branches_recorded_as_failures(conn: sqlite3.Connection):
    """When there IS a survivor, the other branches go to the failure taxonomy."""
    run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=80.0),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=None),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    failures = conn.execute("SELECT approach FROM failures").fetchall()
    assert len(failures) == 1
    assert failures[0][0] == "b1"  # the loser


def test_frame_record_has_resolved_by_after_run(conn: sqlite3.Connection):
    run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=80.0),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=None),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    row = conn.execute("SELECT resolved_by FROM frames").fetchone()
    assert row is not None
    assert row[0] is not None  # filled in after collapse


# ---------------------------------------------------------------------------
# Critical findings


def test_critical_unresolved_finding_kills_a_branch(conn: sqlite3.Connection):
    """A critical unresolved finding on b0 should remove it from contention; b1 wins
    even if b0 also passed verification."""
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary(
            [
                Finding(
                    branch_id="b0",
                    severity="critical",
                    category="security",
                    title="SQL injection",
                    detail="d",
                    resolved=False,
                ),
            ]
        ),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=80.0),
                "b1": VerifyResult(has_tests=True, verified=True, coverage=70.0),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.survivor is not None
    assert report.survivor.id == "b1"


# ---------------------------------------------------------------------------
# Baseline comparison


def test_baseline_comparison_runs_when_baseline_given(conn: sqlite3.Connection):
    baseline = record_baseline(
        conn,
        task="t",
        response="def add(a, b): return a + b",
        tokens_used=100,
        tests_pass=True,
        coverage=70.0,
    )
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier(
            {
                "b0": VerifyResult(has_tests=True, verified=True, coverage=80.0),
                "b1": VerifyResult(has_tests=True, verified=False, coverage=None),
            }
        ),
        budget=Budget(max_usd=10.0),
        conn=conn,
        baseline=baseline,
    )
    assert report.baseline_comparison is not None
    assert isinstance(baseline, Baseline)


def test_no_baseline_means_no_comparison(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier({"b0": VerifyResult(has_tests=True, verified=True, coverage=80.0)}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.baseline_comparison is None


# ---------------------------------------------------------------------------
# Run report shape


def test_report_carries_branch_results(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert len(report.branch_results) == 2
    assert all(isinstance(br, BranchResult) for br in report.branch_results)


def test_report_carries_divergence_when_not_aborted_early(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.divergence is not None


def test_report_is_immutable(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    with pytest.raises((AttributeError, TypeError)):
        report.task = "changed"  # type: ignore[misc]


def test_timestamps_are_set(conn: sqlite3.Connection):
    report = run(
        task="t",
        session_id="s",
        base_prompt="x",
        research=_research(),
        selfeval=_selfeval(),
        generator=_make_generator(_divergent_outputs()),
        adversary=_make_adversary([]),
        verifier=_make_verifier({}),
        budget=Budget(max_usd=10.0),
        conn=conn,
    )
    assert report.started_at > 0
    assert report.finished_at >= report.started_at
