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


def _decide(
    baseline_passes: bool, pqa_passes: bool, responses_different: bool
) -> tuple[Verdict, str]:
    if not baseline_passes and not pqa_passes:
        return "baseline_wins", "neither passed tests — PQA spend was wasted"
    if pqa_passes and not baseline_passes:
        return "pqa_wins", "PQA found a working solution that single-pass missed"
    if baseline_passes and not pqa_passes:
        return "baseline_wins", "regression: PQA broke a working baseline"
    if not responses_different:
        return "tie", "both passed but converged on the same solution — PQA spend was overhead"
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
    verdict, rationale = _decide(baseline.tests_pass, pqa_tests_pass, responses_different)
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
