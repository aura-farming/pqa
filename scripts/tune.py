#!/usr/bin/env python3
"""Propose config diffs from accumulated run telemetry (roadmap §5.3, the
implement half of implement-or-cut).

Reads `cost_runs` (and the signal calibration when present) and prints proposed
`pqa-config.toml` changes it can defend from the data. It never edits config —
tune proposes, the operator decides.

Run:  python3 scripts/tune.py   (uses the configured memory_db)
"""

from __future__ import annotations

import sqlite3
import statistics
import sys
from pathlib import Path

# Make the engine importable when run as `python3 scripts/tune.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pqa.config import PQAConfig, load_or_defaults
from pqa.memory import connect

MIN_RUNS = 10
SLACK_THRESHOLD = 0.5  # p95 cost under half the cap → the cap is slack
ABORT_RATE_THRESHOLD = 0.3


def _p95(values: list[float]) -> float:
    if len(values) == 1:
        return values[0]
    quantiles = statistics.quantiles(values, n=20, method="inclusive")
    return quantiles[-1]


def proposals(conn: sqlite3.Connection, cfg: PQAConfig) -> list[str]:
    """Deterministic, defensible config suggestions — or one honest refusal."""
    rows = conn.execute("SELECT total_cost, budget_usd, status FROM cost_runs").fetchall()
    if len(rows) < MIN_RUNS:
        return [
            f"insufficient data: {len(rows)} recorded runs (need >= {MIN_RUNS}) — "
            "run more tasks before tuning"
        ]

    out: list[str] = []
    costs = [float(r[0]) for r in rows]
    abort_rate = sum(1 for r in rows if r[2] == "abort") / len(rows)
    p95_cost = _p95(sorted(costs))

    if abort_rate >= ABORT_RATE_THRESHOLD:
        out.append(
            f"{abort_rate:.0%} of {len(rows)} runs hit the budget cap (abort) — raise "
            f"run_budget_usd above {p95_cost:.2f} (p95 spend) or drop branches to "
            f"{max(2, cfg.branches - 1)} so each run fits"
        )
    elif p95_cost < cfg.run_budget_usd * SLACK_THRESHOLD:
        out.append(
            f"run_budget_usd = {round(max(p95_cost * 1.5, 0.5), 2)}  # p95 spend over "
            f"{len(rows)} runs is {p95_cost:.2f}; the current {cfg.run_budget_usd} cap "
            "is slack — tighten so a runaway run aborts sooner"
        )

    calibration = conn.execute(
        "SELECT coalesce(level,'none'), avg(coalesce(won,0)), count(*) FROM signals"
        " WHERE won IS NOT NULL GROUP BY level"
    ).fetchall()
    if calibration:
        readable = ", ".join(f"P(win|{lvl})={p:.2f} (n={n})" for lvl, p, n in calibration)
        out.append(f"calibration so far: {readable} — interpret via pqa-self-reflector")

    return out or ["telemetry looks healthy at current settings — nothing to propose"]


def main() -> int:
    cfg = load_or_defaults()
    conn = connect(cfg.memory_db)
    try:
        for line in proposals(conn, cfg):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
