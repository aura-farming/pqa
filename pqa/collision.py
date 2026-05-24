"""Adversary findings model + scoring.

The pqa-adversary subagent attacks every branch and emits structured findings — one issue
per finding, classified by severity. This module is the data model and the scoring adapter
that feeds collapse: how many findings did each branch withstand, and which branches did
the adversary kill outright?

Rule: a critical finding that the branch did *not* resolve is a deadly hit. That branch is
dead regardless of other metrics — no amount of resolved-low-severity findings rescues it.
This is the collision counterpart of "the verifier is truth": findings are evidence, and
critical unresolved evidence is fatal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]

# Weights tuned so one resolved critical beats five resolved lows. Tune later from
# self-reflector telemetry once we have outcome data.
SEVERITY_WEIGHTS: dict[Severity, float] = {
    "critical": 8.0,
    "high": 4.0,
    "medium": 2.0,
    "low": 1.0,
}


@dataclass(frozen=True)
class Finding:
    branch_id: str
    severity: Severity
    category: str
    title: str
    detail: str
    resolved: bool = False


@dataclass(frozen=True)
class CollisionScore:
    branch_id: str
    total: int
    resolved: int
    critical_unresolved: int
    weighted_score: float

    @property
    def survives(self) -> bool:
        """A critical unresolved finding is a deadly hit — the branch is dead."""
        return self.critical_unresolved == 0


def score_branch(branch_id: str, findings: list[Finding]) -> CollisionScore:
    """Score one branch against the full findings list. Only findings whose branch_id
    matches contribute."""
    matched = [f for f in findings if f.branch_id == branch_id]
    total = len(matched)
    resolved = sum(1 for f in matched if f.resolved)
    critical_unresolved = sum(1 for f in matched if f.severity == "critical" and not f.resolved)
    weighted = sum(SEVERITY_WEIGHTS[f.severity] for f in matched if f.resolved)
    return CollisionScore(
        branch_id=branch_id,
        total=total,
        resolved=resolved,
        critical_unresolved=critical_unresolved,
        weighted_score=weighted,
    )


def score_all(
    findings: list[Finding], branch_ids: list[str] | None = None
) -> dict[str, CollisionScore]:
    """Score every branch. Pass `branch_ids` to include clean branches (the adversary
    found nothing wrong with them) — without it, branches with zero findings vanish from
    the dict because they don't appear in the findings list."""
    ids = set(branch_ids) if branch_ids is not None else {f.branch_id for f in findings}
    return {bid: score_branch(bid, findings) for bid in ids}
