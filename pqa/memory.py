"""Persistence layer for PQA memory. Stdlib sqlite3 only.

Three things persist across sessions: named precipitates (what won and why), the failure
taxonomy (what died and why — the continuous-learning asset), and conviction signals
(instinct-vs-reality telemetry). Frame disagreements are recorded by the harness directly.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = Path(__file__).resolve().parent.parent / "hooks" / "memory" / "schema.sql"


@dataclass(frozen=True)
class Failure:
    approach: str
    death_reason: str
    conviction: str = "none"


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    fresh = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    if fresh and _SCHEMA.exists():
        conn.executescript(_SCHEMA.read_text())
        conn.commit()
    return conn


def record_precipitate(conn: sqlite3.Connection, session: str, task: str, name: str,
                       rationale: str, domain: str | None = None) -> None:
    conn.execute(
        "INSERT INTO precipitates(session_id, task, name, rationale, domain, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (session, task, name, rationale, domain, int(time.time())),
    )
    conn.commit()


def record_failure(conn: sqlite3.Connection, session: str, task: str, failure: Failure) -> None:
    conn.execute(
        "INSERT INTO failures(session_id, task, approach, death_reason, conviction, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (session, task, failure.approach, failure.death_reason, failure.conviction, int(time.time())),
    )
    conn.commit()


def recent_failures(conn: sqlite3.Connection, limit: int = 10) -> list[tuple[str, str]]:
    """Approaches that have already died, newest first — feeds frame loading so the harness
    does not re-propose a known-dead approach."""
    cur = conn.execute(
        "SELECT approach, death_reason FROM failures ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]
