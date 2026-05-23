"""Collapse: converge a superposition to one survivor on evidence.

This is the correctness core. The rule is strict and deliberately boring: evidence first,
eloquence never. A branch is accepted only if it passed verification; conviction changes
nothing here. Among verified branches, the survivor resolves the most adversary findings;
ties break toward the less incremental branch (the quantum jump).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BranchResult:
    """Objective outcome for one branch after collision + verification."""
    name: str
    verified: bool                 # passed the real test suite
    has_tests: bool                # whether a suite existed to verify against
    coverage: float | None         # % coverage, or None if unmeasured
    findings_resolved: int         # adversary findings this branch withstands/handles
    findings_total: int            # adversary findings raised against it
    conviction: str | None         # high/medium/low/None — telemetry only, never decisive
    incremental: bool              # True = safe/obvious; False = bigger swing


@dataclass(frozen=True)
class CollapseOutcome:
    survivor: BranchResult | None
    reason: str
    unverified: bool               # True when no branch could be tested
    confidence: str                # human-readable qualifier on the result


def _confidence(branch: BranchResult) -> str:
    if not branch.has_tests:
        return "UNVERIFIED — no test suite; accepted on adversary findings only"
    if branch.coverage is None:
        return "verified (coverage unmeasured)"
    if branch.coverage < 50:
        return f"passes-but-thinly-tested ({branch.coverage:.0f}% coverage)"
    return f"verified ({branch.coverage:.0f}% coverage)"


def _rank_key(b: BranchResult) -> tuple[int, float, int]:
    # higher findings_resolved, then higher coverage, then the quantum jump (non-incremental).
    return (b.findings_resolved, b.coverage or 0.0, 0 if b.incremental else 1)


def select_survivor(results: list[BranchResult]) -> CollapseOutcome:
    if not results:
        return CollapseOutcome(None, "no branches to collapse", False, "n/a")

    any_tests = any(b.has_tests for b in results)
    if any_tests:
        verified = [b for b in results if b.verified]
        if not verified:
            return CollapseOutcome(
                None, "all branches failed verification", False,
                "no survivor — every branch failed its tests",
            )
        winner = max(verified, key=_rank_key)
        return CollapseOutcome(winner, "survived attack and passed tests", False, _confidence(winner))

    # No suite anywhere: collapse on adversary findings only, clearly flagged.
    winner = max(results, key=lambda b: (b.findings_resolved, 0 if b.incremental else 1))
    return CollapseOutcome(winner, "no test suite; chosen on adversary findings", True, _confidence(winner))
