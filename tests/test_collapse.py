"""Tests for the collapse core — survivor selection must be evidence-first.

These encode the non-negotiable rules: conviction never beats verification; all-fail yields
no survivor; ties break to the bigger swing; no-suite yields an UNVERIFIED result.
"""
from pqa.collapse import BranchResult, select_survivor


def _branch(name, verified=True, has_tests=True, coverage=80.0,
            resolved=5, total=5, conviction=None, incremental=True):
    return BranchResult(name, verified, has_tests, coverage, resolved, total, conviction, incremental)


def test_unverified_high_conviction_loses_to_verified_plain():
    # The whole point of PQA: instinct does not beat evidence.
    flashy = _branch("flashy", verified=False, conviction="high", resolved=9, total=9)
    plain = _branch("plain", verified=True, conviction=None, resolved=4, total=5)
    outcome = select_survivor([flashy, plain])
    assert outcome.survivor is not None
    assert outcome.survivor.name == "plain"


def test_all_branches_fail_yields_no_survivor():
    outcome = select_survivor([
        _branch("a", verified=False),
        _branch("b", verified=False),
    ])
    assert outcome.survivor is None
    assert "failed" in outcome.reason


def test_tie_breaks_toward_non_incremental_quantum_jump():
    safe = _branch("safe", resolved=6, coverage=80.0, incremental=True)
    bold = _branch("bold", resolved=6, coverage=80.0, incremental=False)
    outcome = select_survivor([safe, bold])
    assert outcome.survivor.name == "bold"


def test_more_resolved_findings_wins():
    weak = _branch("weak", resolved=2)
    strong = _branch("strong", resolved=7)
    assert select_survivor([weak, strong]).survivor.name == "strong"


def test_no_test_suite_is_flagged_unverified():
    outcome = select_survivor([
        _branch("a", has_tests=False, coverage=None, resolved=3),
        _branch("b", has_tests=False, coverage=None, resolved=5),
    ])
    assert outcome.unverified is True
    assert outcome.survivor.name == "b"
    assert "UNVERIFIED" in outcome.confidence


def test_thin_coverage_is_labelled_honestly():
    outcome = select_survivor([_branch("a", coverage=12.0)])
    assert "thinly-tested" in outcome.confidence


def test_empty_input_is_safe():
    outcome = select_survivor([])
    assert outcome.survivor is None
