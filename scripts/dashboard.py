#!/usr/bin/env python3
"""PQA dashboard. Renders the accumulating memory — the product's moat — as a terminal report.

Stdlib only and cross-platform (no Tkinter, no deps), consistent with the rest of PQA. Reads
the SQLite memory DB written by the precipitate-capture hook and the memory curator.

Usage:  python scripts/dashboard.py [path-to-pqa_memory.db]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

DEFAULT_DB = ".claude/hooks/memory/pqa_memory.db"


_COUNT_TABLES = frozenset({"precipitates", "failures", "signals", "frames", "instincts"})


def _count(conn: sqlite3.Connection, table: str) -> int:
    # Table name is constrained to a small allow-list, so f-string interpolation here is safe.
    if table not in _COUNT_TABLES:
        return 0
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
    except sqlite3.Error:
        return 0


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple[Any, ...]]:
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def render(db: Path) -> str:
    if not db.exists():
        return f"No PQA memory yet at {db}. Run /pqa and /precipitate first."
    conn = sqlite3.connect(str(db))
    out: list[str] = ["PQA MEMORY DASHBOARD", "=" * 60]
    out.append(
        f"precipitates: {_count(conn, 'precipitates')}   "
        f"failures: {_count(conn, 'failures')}   "
        f"signals: {_count(conn, 'signals')}   "
        f"instincts: {_count(conn, 'instincts')}"
    )

    out.append("\nRecent precipitates (what won, and why):")
    for name, why in _rows(
        conn, "SELECT name, rationale FROM precipitates ORDER BY created_at DESC, id DESC LIMIT 8"
    ):
        out.append(f"  + {name}: {why}")

    out.append("\nTop failed approaches (the moat — what doesn't work):")
    for approach, n in _rows(
        conn, "SELECT approach, COUNT(*) c FROM failures GROUP BY approach ORDER BY c DESC LIMIT 8"
    ):
        out.append(f"  - {approach}  (died {n}x)")

    out.append("\nConviction calibration (P(win) per flagged level vs base rate):")
    for level, n, wins, pending in _rows(
        conn,
        "SELECT level, count(CASE WHEN outcome_at IS NOT NULL THEN 1 END), "
        "sum(CASE WHEN outcome_at IS NOT NULL AND won = 1 THEN 1 ELSE 0 END), "
        "count(CASE WHEN outcome_at IS NULL THEN 1 END) "
        "FROM signals GROUP BY level ORDER BY level",
    ):
        rate = f"P(win)={(wins or 0) / n:.2f} ({wins or 0}/{n})" if n else "no outcomes yet"
        suffix = f", {pending} pending back-fill" if pending else ""
        out.append(f"  {level}: {rate}{suffix}")
    for precip, merit_deaths in _rows(
        conn,
        "SELECT (SELECT count(*) FROM precipitates), "
        "(SELECT count(*) FROM failures WHERE death_reason NOT LIKE 'budget:%')",
    ):
        total = precip + merit_deaths
        if total:
            out.append(f"  base (all branches): {precip / total:.2f} ({precip}/{total})")

    out.append("\nInstincts (synthesized + imported, by confidence):")
    for name, confidence, evidence_n, origin in _rows(
        conn,
        "SELECT name, confidence, evidence_n, origin FROM instincts "
        "ORDER BY confidence DESC, name LIMIT 6",
    ):
        out.append(f"  * {name} ({confidence:.2f}, n={evidence_n}, {origin})")

    conn.close()
    return "\n".join(out)


def main(argv: list[str]) -> int:
    db = Path(argv[1]) if len(argv) > 1 else Path(DEFAULT_DB)
    print(render(db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
