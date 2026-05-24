"""Tests for the adversary collision model.

The adversary attacks every branch and emits structured findings. collision.py turns those
findings into a per-branch score the orchestrator feeds into collapse. A critical finding
that the branch did not resolve is fatal — that branch is dead regardless of other metrics.
"""

import pytest

from pqa.collision import (
    SEVERITY_WEIGHTS,
    CollisionScore,
    Finding,
    score_all,
    score_branch,
)


def _f(branch_id="b", severity="medium", resolved=False, category="correctness", **rest) -> Finding:
    defaults = {
        "branch_id": branch_id,
        "severity": severity,
        "category": category,
        "title": "T",
        "detail": "D",
        "resolved": resolved,
    }
    defaults.update(rest)
    return Finding(**defaults)


def test_score_branch_empty_findings_returns_zeros():
    score = score_branch("b1", [])
    assert score.branch_id == "b1"
    assert score.total == 0
    assert score.resolved == 0
    assert score.critical_unresolved == 0
    assert score.weighted_score == 0.0


def test_score_branch_counts_only_matching_branch():
    findings = [
        _f(branch_id="b1", resolved=True),
        _f(branch_id="b1", resolved=False),
        _f(branch_id="b2", resolved=True),
    ]
    score = score_branch("b1", findings)
    assert score.total == 2
    assert score.resolved == 1


def test_critical_unresolved_kills_survival():
    findings = [_f(branch_id="b1", severity="critical", resolved=False)]
    score = score_branch("b1", findings)
    assert score.critical_unresolved == 1
    assert score.survives is False


def test_critical_resolved_does_not_kill_survival():
    findings = [_f(branch_id="b1", severity="critical", resolved=True)]
    score = score_branch("b1", findings)
    assert score.critical_unresolved == 0
    assert score.survives is True


def test_branch_with_no_findings_survives():
    score = score_branch("b1", [])
    assert score.survives is True


def test_weighted_score_uses_severity_weights():
    # Two resolved findings: one critical (8) + one low (1) → weighted = 9.
    findings = [
        _f(branch_id="b1", severity="critical", resolved=True),
        _f(branch_id="b1", severity="low", resolved=True),
    ]
    score = score_branch("b1", findings)
    assert score.weighted_score == pytest.approx(9.0)


def test_unresolved_findings_do_not_count_toward_weighted_score():
    findings = [
        _f(branch_id="b1", severity="critical", resolved=False),
        _f(branch_id="b1", severity="high", resolved=False),
    ]
    score = score_branch("b1", findings)
    assert score.weighted_score == 0.0


def test_resolved_critical_outweighs_many_resolved_lows():
    # One critical resolved (8) beats five low resolved (5).
    crit = score_branch("b1", [_f(branch_id="b1", severity="critical", resolved=True)])
    lows = score_branch("b2", [_f(branch_id="b2", severity="low", resolved=True) for _ in range(5)])
    assert crit.weighted_score > lows.weighted_score


def test_score_all_groups_by_branch():
    findings = [
        _f(branch_id="b1", resolved=True),
        _f(branch_id="b1", resolved=False),
        _f(branch_id="b2", resolved=True),
    ]
    scores = score_all(findings)
    assert set(scores.keys()) == {"b1", "b2"}
    assert scores["b1"].total == 2
    assert scores["b2"].total == 1


def test_score_all_includes_clean_branches_when_branch_ids_passed():
    # A branch the adversary found nothing wrong with is still alive — it just has zero
    # findings. score_all must include it when given the full branch_ids list.
    findings = [_f(branch_id="b1", resolved=True)]
    scores = score_all(findings, branch_ids=["b1", "clean"])
    assert "clean" in scores
    assert scores["clean"].total == 0
    assert scores["clean"].survives is True


def test_score_all_with_empty_findings_and_branch_ids():
    scores = score_all([], branch_ids=["a", "b"])
    assert set(scores.keys()) == {"a", "b"}
    assert all(s.total == 0 and s.survives for s in scores.values())


def test_severity_weights_have_expected_ordering():
    assert (
        SEVERITY_WEIGHTS["critical"]
        > SEVERITY_WEIGHTS["high"]
        > SEVERITY_WEIGHTS["medium"]
        > SEVERITY_WEIGHTS["low"]
    )


def test_severity_weights_cover_all_levels():
    assert set(SEVERITY_WEIGHTS.keys()) == {"critical", "high", "medium", "low"}


def test_finding_is_immutable():
    finding = _f()
    with pytest.raises((AttributeError, TypeError)):
        finding.resolved = True  # type: ignore[misc]


def test_collision_score_is_immutable():
    score = CollisionScore(
        branch_id="b1", total=0, resolved=0, critical_unresolved=0, weighted_score=0.0
    )
    with pytest.raises((AttributeError, TypeError)):
        score.weighted_score = 99.0  # type: ignore[misc]


def test_finding_default_resolved_is_false():
    f = Finding(branch_id="b", severity="medium", category="c", title="t", detail="d")
    assert f.resolved is False


def test_multiple_critical_unresolved_all_count():
    findings = [
        _f(branch_id="b1", severity="critical", resolved=False),
        _f(branch_id="b1", severity="critical", resolved=False),
    ]
    score = score_branch("b1", findings)
    assert score.critical_unresolved == 2
    assert score.survives is False


def test_a_branch_with_high_severity_unresolved_still_survives():
    # Only "critical" unresolved is fatal. High/medium/low unresolved hurt the score but
    # are not deadly hits.
    findings = [
        _f(branch_id="b1", severity="high", resolved=False),
        _f(branch_id="b1", severity="medium", resolved=False),
        _f(branch_id="b1", severity="low", resolved=False),
    ]
    score = score_branch("b1", findings)
    assert score.critical_unresolved == 0
    assert score.survives is True
    assert score.weighted_score == 0.0


def test_score_all_groups_correctly_for_realistic_run():
    findings = [
        _f(branch_id="b1", severity="critical", resolved=True),
        _f(branch_id="b1", severity="medium", resolved=False),
        _f(branch_id="b2", severity="critical", resolved=False),
        _f(branch_id="b2", severity="low", resolved=True),
        _f(branch_id="b3", severity="high", resolved=True),
    ]
    scores = score_all(findings)
    assert scores["b1"].survives is True  # critical resolved
    assert scores["b2"].survives is False  # critical NOT resolved
    assert scores["b3"].survives is True  # high resolved
    assert scores["b1"].weighted_score == pytest.approx(SEVERITY_WEIGHTS["critical"])
    assert scores["b3"].weighted_score == pytest.approx(SEVERITY_WEIGHTS["high"])
