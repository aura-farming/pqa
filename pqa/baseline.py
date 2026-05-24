"""Baseline comparator: store the single-pass first attempt and score PQA's converged
solution against it.

The headline claim of PQA is "beats the single-pass baseline." Without recording and
comparing the baseline side-by-side, that claim is unmeasurable. The verdict logic is
strict on purpose: same answer, more spend = a tie (= a loss in cost terms). PQA only
wins by producing a different, working solution.
"""

from __future__ import annotations

import difflib
import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["pqa_wins", "baseline_wins", "tie"]

# Below this SequenceMatcher ratio, two responses are considered demonstrably different.
# Tuned so a whitespace/style reformat still counts as "same algorithm".
DIFFERENT_BELOW = 0.85

# Cost-regression threshold: even a different working solution loses to the baseline
# in the token-cost dimension if PQA spent more than this multiple of the baseline's
# token cost. Tuned conservatively — PQA SHOULD cost more than single-pass (it runs N
# branches + adversary + verifier), but if it costs N+1x more without proportionate
# quality gain, the trade-off is bad. A team comparing PQA-vs-single-pass should be
# allowed to see this in the verdict, not have it buried in a delta column.
COST_REGRESSION_FACTOR = 10.0


@dataclass(frozen=True)
class Baseline:
    task: str
    response: str
    tokens_used: int
    tests_pass: bool
    coverage: float | None
    created_at: int


@dataclass(frozen=True)
class Comparison:
    task: str
    baseline: Baseline
    pqa_response: str
    pqa_tokens_used: int
    pqa_tests_pass: bool
    pqa_coverage: float | None
    verdict: Verdict
    rationale: str


def record_baseline(
    conn: sqlite3.Connection,
    task: str,
    response: str,
    tokens_used: int,
    tests_pass: bool,
    coverage: float | None = None,
) -> Baseline:
    if not task:
        raise ValueError("task must be a non-empty string")
    if tokens_used < 0:
        raise ValueError(f"tokens_used must be non-negative, got {tokens_used}")
    created_at = int(time.time())
    conn.execute(
        "INSERT INTO baselines(task, response, tokens_used, tests_pass, coverage, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (task, response, tokens_used, 1 if tests_pass else 0, coverage, created_at),
    )
    conn.commit()
    return Baseline(
        task=task,
        response=response,
        tokens_used=tokens_used,
        tests_pass=tests_pass,
        coverage=coverage,
        created_at=created_at,
    )


def get_baseline(conn: sqlite3.Connection, task: str) -> Baseline | None:
    """Return the most recent baseline for a task, or None if there isn't one yet."""
    row = conn.execute(
        "SELECT task, response, tokens_used, tests_pass, coverage, created_at "
        "FROM baselines WHERE task = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (task,),
    ).fetchone()
    if row is None:
        return None
    return Baseline(
        task=row[0],
        response=row[1],
        tokens_used=row[2],
        tests_pass=bool(row[3]),
        coverage=row[4],
        created_at=row[5],
    )


def _similarity(a: str, b: str) -> float:
    """0.0 = totally different, 1.0 = identical. Whitespace stripped so trivial style
    diffs do not count as different solutions."""
    return difflib.SequenceMatcher(None, "".join(a.split()), "".join(b.split())).ratio()


def _is_cost_regression(baseline_tokens: int, pqa_tokens: int) -> bool:
    """True iff PQA spent more than COST_REGRESSION_FACTOR x the baseline. A working
    PQA solution that costs 50x more than the single-pass baseline is not a clean
    'win' — the operator should see the cost overhead in the verdict rather than
    finding it later in a token-delta column."""
    if baseline_tokens <= 0:
        # Without a positive baseline cost we cannot compute the ratio honestly.
        return False
    return pqa_tokens > baseline_tokens * COST_REGRESSION_FACTOR


def _decide(
    baseline_passes: bool,
    pqa_passes: bool,
    responses_different: bool,
    cost_regression: bool,
) -> tuple[Verdict, str]:
    if not baseline_passes and not pqa_passes:
        return "baseline_wins", "neither passed tests — PQA spend was wasted"
    if pqa_passes and not baseline_passes:
        # Even a cost-regressed win is still a win when single-pass produced nothing
        # workable — solving the problem at all is the dominant signal.
        return "pqa_wins", "PQA found a working solution that single-pass missed"
    if baseline_passes and not pqa_passes:
        return "baseline_wins", "regression: PQA broke a working baseline"
    if not responses_different:
        return "tie", "both passed but converged on the same solution — PQA spend was overhead"
    if cost_regression:
        return (
            "tie",
            "both passed with different solutions but PQA cost > "
            f"{COST_REGRESSION_FACTOR:.0f}x the baseline — quality gain did not justify spend",
        )
    return (
        "pqa_wins",
        "both passed and PQA produced a demonstrably different (non-obvious) solution",
    )


def compare(
    baseline: Baseline,
    pqa_response: str,
    pqa_tokens_used: int,
    pqa_tests_pass: bool,
    pqa_coverage: float | None = None,
) -> Comparison:
    similarity = _similarity(baseline.response, pqa_response)
    responses_different = similarity < DIFFERENT_BELOW
    cost_regression = _is_cost_regression(baseline.tokens_used, pqa_tokens_used)
    verdict, rationale = _decide(
        baseline.tests_pass, pqa_tests_pass, responses_different, cost_regression
    )
    return Comparison(
        task=baseline.task,
        baseline=baseline,
        pqa_response=pqa_response,
        pqa_tokens_used=pqa_tokens_used,
        pqa_tests_pass=pqa_tests_pass,
        pqa_coverage=pqa_coverage,
        verdict=verdict,
        rationale=rationale,
    )
