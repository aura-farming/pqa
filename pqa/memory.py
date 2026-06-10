"""Persistence layer for PQA memory. Stdlib sqlite3 only.

Three things persist across sessions: named precipitates (what won and why), the failure
taxonomy (what died and why — the continuous-learning asset), and conviction signals
(instinct-vs-reality telemetry). Frame disagreements are recorded by the harness directly.

Retrieval is relevance-first (roadmap §4.3): an FTS5 index over precipitates and failures
is created at connect() time when the SQLite build ships FTS5, and search degrades to
LIKE keyword-scoring when it does not. Migrations never contain FTS5 DDL — the schema
must apply on every build, indexed or not.
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pqa.cost import estimate_tokens
from pqa.migrations import apply_migrations, discover_migrations

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "memory" / "migrations"

SIGNAL_LEVELS: tuple[str, ...] = ("high", "medium", "low")

# table -> columns carried in its FTS index. Both content tables are append-only,
# which is what makes the count-equality drift check in _ensure_fts_index sound.
# The S608 suppressions throughout this file exist because table/column fragments
# in SQL come from this constant (or a fixed column set), never from caller input —
# all values travel as bound parameters.
_FTS_SPECS: dict[str, tuple[str, ...]] = {
    "precipitates": ("name", "rationale", "task", "domain"),
    "failures": ("approach", "death_reason", "task"),
}

_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_MAX_QUERY_TOKENS = 12

_PRIOR_ART_HEADER = "Prior art from PQA memory (cite ids; do not re-propose dead approaches):"


@dataclass(frozen=True)
class Failure:
    approach: str
    death_reason: str
    conviction: str = "none"


@dataclass(frozen=True)
class PrecipitateHit:
    id: int
    name: str
    rationale: str
    task: str | None
    domain: str | None


@dataclass(frozen=True)
class FailureHit:
    id: int
    approach: str
    death_reason: str
    task: str | None
    conviction: str | None


@dataclass(frozen=True)
class InstinctHit:
    id: int
    name: str
    statement: str
    confidence: float


@dataclass(frozen=True)
class PriorArt:
    """The bounded prior-art block injected at frame-load: composed text plus the ids
    of every memory it cites, so the run report can name what influenced the run."""

    ids: tuple[str, ...]
    text: str


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the PQA memory database, applying any pending migrations and (when the
    SQLite build supports it) ensuring the FTS5 search index exists and is in sync.
    Idempotent — calling this on an up-to-date DB is a no-op."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    if _MIGRATIONS_DIR.exists():
        apply_migrations(conn, discover_migrations(_MIGRATIONS_DIR))
    _ensure_fts_index(conn)
    return conn


def fts5_available(conn: sqlite3.Connection) -> bool:
    """Probe whether this SQLite build was compiled with the FTS5 module."""
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.__pqa_fts_probe USING fts5(probe)")
        conn.execute("DROP TABLE temp.__pqa_fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _fts_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (f"{table}_fts",)
    ).fetchone()
    return row is not None


def _ensure_fts_index(conn: sqlite3.Connection) -> None:
    """Create the external-content FTS5 tables and repair drift. Rows written by an
    FTS5-less build (e.g. a stdlib hook on another machine) are not indexed at write
    time; because the content tables are append-only, a count mismatch detects that
    drift exactly, and 'rebuild' re-derives the index from the content table."""
    if not fts5_available(conn):
        return
    for table, cols in _FTS_SPECS.items():
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table}_fts USING fts5("
            f"{', '.join(cols)}, content='{table}', content_rowid='id')"
        )
        n_content = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
        # count(*) on an external-content FTS table reads through to the content table
        # and can never disagree with it; the docsize shadow table is the real count of
        # *indexed* documents, which is the side that drifts.
        n_indexed = conn.execute(
            f"SELECT count(*) FROM {table}_fts_docsize"  # noqa: S608
        ).fetchone()[0]
        if n_content != n_indexed:
            conn.execute(f"INSERT INTO {table}_fts({table}_fts) VALUES('rebuild')")
    conn.commit()


def _fts_write_through(
    conn: sqlite3.Connection, table: str, rowid: int | None, values: tuple[str | None, ...]
) -> None:
    """Mirror a freshly inserted content row into its FTS index, when present. On a
    build without FTS5 reading a DB that carries the index table, the INSERT raises
    OperationalError and is skipped deliberately — the next FTS5-capable connect()
    repairs the index via the drift rebuild, so nothing is lost, only deferred."""
    if rowid is None or not _fts_table_exists(conn, table):
        return
    cols = _FTS_SPECS[table]
    with contextlib.suppress(sqlite3.OperationalError):
        conn.execute(
            f"INSERT INTO {table}_fts(rowid, {', '.join(cols)}) VALUES(?{', ?' * len(cols)})",
            (rowid, *values),
        )


def record_precipitate(
    conn: sqlite3.Connection,
    session: str,
    task: str,
    name: str,
    rationale: str,
    domain: str | None = None,
) -> None:
    cur = conn.execute(
        "INSERT INTO precipitates(session_id, task, name, rationale, domain, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (session, task, name, rationale, domain, int(time.time())),
    )
    _fts_write_through(conn, "precipitates", cur.lastrowid, (name, rationale, task, domain))
    conn.commit()


def record_failure(conn: sqlite3.Connection, session: str, task: str, failure: Failure) -> None:
    cur = conn.execute(
        "INSERT INTO failures(session_id, task, approach, death_reason, conviction, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (
            session,
            task,
            failure.approach,
            failure.death_reason,
            failure.conviction,
            int(time.time()),
        ),
    )
    _fts_write_through(
        conn, "failures", cur.lastrowid, (failure.approach, failure.death_reason, task)
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


def record_signal(
    conn: sqlite3.Connection,
    session: str,
    level: str,
    basis: str,
    branch: str | None = None,
) -> int:
    """Record a conviction signal the moment it is raised. Outcomes (survived /
    verified / won) are unknown at this point — update_signal_outcome back-fills
    them after collapse. Returns the new signal's id for that back-fill."""
    if level not in SIGNAL_LEVELS:
        raise ValueError(f"signal level must be one of {SIGNAL_LEVELS}, got {level!r}")
    cur = conn.execute(
        "INSERT INTO signals(session_id, level, basis, branch, created_at) VALUES(?,?,?,?,?)",
        (session, level, basis, branch, int(time.time())),
    )
    conn.commit()
    if cur.lastrowid is None:  # pragma: no cover — sqlite always sets it after INSERT
        raise RuntimeError("sqlite returned no rowid for the signal insert")
    return cur.lastrowid


def _outcome_assignments(
    survived: bool | None, verified: bool | None, won: bool | None
) -> dict[str, int]:
    """The outcome columns actually provided (None = still unknown, not written)."""
    provided = {
        col: int(flag)
        for col, flag in (("survived", survived), ("verified", verified), ("won", won))
        if flag is not None
    }
    if not provided:
        raise ValueError("at least one outcome (survived/verified/won) must be provided")
    return provided


def update_signal_outcome(
    conn: sqlite3.Connection,
    signal_id: int,
    *,
    survived: bool | None = None,
    verified: bool | None = None,
    won: bool | None = None,
) -> bool:
    """Back-fill what actually happened to a flagged branch: survived the adversary
    collision, passed the verifier, won the collapse. Only outcomes passed as
    booleans are written (None = still unknown). Returns False for an unknown id."""
    provided = _outcome_assignments(survived, verified, won)
    assignments = ", ".join(f"{col} = ?" for col in provided)
    cur = conn.execute(
        f"UPDATE signals SET {assignments}, outcome_at = ? WHERE id = ?",  # noqa: S608
        (*provided.values(), int(time.time()), signal_id),
    )
    conn.commit()
    return cur.rowcount > 0


def backfill_signal_outcomes(
    conn: sqlite3.Connection,
    session: str,
    branch: str | None = None,
    *,
    survived: bool | None = None,
    verified: bool | None = None,
    won: bool | None = None,
) -> int:
    """Back-fill outcomes on every still-pending signal of a session (optionally one
    branch) — the path for hook-captured signals whose ids the caller never saw.
    Settled rows (outcome_at already set) are never touched. Returns rows updated."""
    provided = _outcome_assignments(survived, verified, won)
    assignments = ", ".join(f"{col} = ?" for col in provided)
    where = "session_id = ? AND outcome_at IS NULL"
    params: tuple[int | str, ...] = (*provided.values(), int(time.time()), session)
    if branch is not None:
        where += " AND branch = ?"
        params += (branch,)
    cur = conn.execute(
        f"UPDATE signals SET {assignments}, outcome_at = ? WHERE {where}",  # noqa: S608
        params,
    )
    conn.commit()
    return cur.rowcount


def _query_tokens(query: str) -> list[str]:
    """Lowercased, deduplicated word tokens — the only thing that ever reaches the
    FTS MATCH grammar or a LIKE pattern, so hostile query syntax cannot escape."""
    seen: dict[str, None] = {}
    for token in _TOKEN.findall(query.lower()):
        if len(token) > 1:
            seen.setdefault(token, None)
    return list(seen)[:_MAX_QUERY_TOKENS]


def _fts_search(
    conn: sqlite3.Connection, table: str, columns: str, tokens: list[str], limit: int
) -> list[tuple[Any, ...]]:
    match = " OR ".join(f'"{t}"' for t in tokens)
    return conn.execute(
        f"SELECT {columns} FROM {table}_fts JOIN {table} t ON t.id = {table}_fts.rowid "  # noqa: S608
        f"WHERE {table}_fts MATCH ? ORDER BY {table}_fts.rank LIMIT ?",
        (match, limit),
    ).fetchall()


def _like_search(
    conn: sqlite3.Connection,
    table: str,
    columns: str,
    haystack: str,
    tokens: list[str],
    limit: int,
) -> list[tuple[Any, ...]]:
    """Fallback relevance scoring without FTS5: one point per query token found in the
    haystack, recency as the tiebreak. Same contract as the FTS path, coarser ranking."""
    score = " + ".join(f"(CASE WHEN {haystack} LIKE ? THEN 1 ELSE 0 END)" for _ in tokens)
    rows: list[tuple[Any, ...]] = conn.execute(
        f"SELECT * FROM (SELECT {columns}, ({score}) AS relevance FROM {table}) "  # noqa: S608
        "WHERE relevance > 0 ORDER BY relevance DESC, id DESC LIMIT ?",
        (*(f"%{t}%" for t in tokens), limit),
    ).fetchall()
    return [row[:-1] for row in rows]


def search_failures(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[FailureHit]:
    """Top-`limit` failures by relevance to the query — what died near this task before."""
    tokens = _query_tokens(query)
    if not tokens:
        return []
    if _fts_table_exists(conn, "failures"):
        try:
            rows = _fts_search(
                conn,
                "failures",
                "t.id, t.approach, t.death_reason, t.task, t.conviction",
                tokens,
                limit,
            )
            return [FailureHit(*row) for row in rows]
        except sqlite3.OperationalError:
            pass  # index table exists but this build lacks FTS5 — degrade to LIKE
    rows = _like_search(
        conn,
        "failures",
        "id, approach, death_reason, task, conviction",
        "approach || ' ' || death_reason || ' ' || coalesce(task,'')",
        tokens,
        limit,
    )
    return [FailureHit(*row) for row in rows]


def search_precipitates(
    conn: sqlite3.Connection, query: str, limit: int = 5
) -> list[PrecipitateHit]:
    """Top-`limit` precipitates by relevance to the query — what won near this task before."""
    tokens = _query_tokens(query)
    if not tokens:
        return []
    if _fts_table_exists(conn, "precipitates"):
        try:
            rows = _fts_search(
                conn,
                "precipitates",
                "t.id, t.name, t.rationale, t.task, t.domain",
                tokens,
                limit,
            )
            return [PrecipitateHit(*row) for row in rows]
        except sqlite3.OperationalError:
            pass  # index table exists but this build lacks FTS5 — degrade to LIKE
    rows = _like_search(
        conn,
        "precipitates",
        "id, name, rationale, task, domain",
        "name || ' ' || rationale || ' ' || coalesce(task,'') || ' ' || coalesce(domain,'')",
        tokens,
        limit,
    )
    return [PrecipitateHit(*row) for row in rows]


def search_instincts(conn: sqlite3.Connection, query: str, limit: int = 3) -> list[InstinctHit]:
    """Top-`limit` instincts by relevance, confidence as the tiebreak. Always
    LIKE-scored, never FTS: instincts are updated in place by re-synthesis, and the
    FTS drift repair assumes append-only content tables."""
    tokens = _query_tokens(query)
    if not tokens:
        return []
    score = " + ".join("(CASE WHEN haystack LIKE ? THEN 1 ELSE 0 END)" for _ in tokens)
    rows = conn.execute(
        "SELECT id, name, statement, confidence FROM ("  # noqa: S608
        f"SELECT id, name, statement, confidence, ({score}) AS relevance "
        "FROM (SELECT id, name, statement, confidence, "
        "name || ' ' || statement AS haystack FROM instincts)) "
        "WHERE relevance > 0 ORDER BY relevance DESC, confidence DESC, id DESC LIMIT ?",
        (*(f"%{t}%" for t in tokens), limit),
    ).fetchall()
    return [InstinctHit(*row) for row in rows]


def instinct_statement(conn: sqlite3.Connection, instinct_id: int) -> str | None:
    """The statement text of one instinct, for agreement telemetry. None if unknown."""
    row = conn.execute("SELECT statement FROM instincts WHERE id = ?", (instinct_id,)).fetchone()
    return None if row is None else str(row[0])


def prior_art(
    conn: sqlite3.Connection, task: str, *, max_tokens: int = 400, k: int = 5
) -> PriorArt:
    """Compose the bounded prior-art block injected at frame-load: top-k relevant
    failures (what not to re-propose), then instincts (distilled cross-run guidance),
    then precipitates (what won before), cut to the token budget in that order. Every
    cited id appears in the text, so the run report's `memories_injected` is auditable
    against the prompt that was built."""
    if max_tokens <= 0:
        return PriorArt(ids=(), text="")
    candidates = (
        [
            (f"failure:{hit.id}", f"- [failure:{hit.id}] {hit.approach}: {hit.death_reason}")
            for hit in search_failures(conn, task, limit=k)
        ]
        + [
            (
                f"instinct:{hit.id}",
                f"- [instinct:{hit.id}] {hit.name}: {hit.statement} "
                f"(confidence {hit.confidence:.2f})",
            )
            for hit in search_instincts(conn, task, limit=3)
        ]
        + [
            (f"precipitate:{hit.id}", f"- [precipitate:{hit.id}] {hit.name}: {hit.rationale}")
            for hit in search_precipitates(conn, task, limit=k)
        ]
    )
    ids: list[str] = []
    lines: list[str] = []
    for memory_id, line in candidates:
        if estimate_tokens("\n".join([_PRIOR_ART_HEADER, *lines, line])) > max_tokens:
            break
        ids.append(memory_id)
        lines.append(line)
    if not lines:
        return PriorArt(ids=(), text="")
    return PriorArt(ids=tuple(ids), text="\n".join([_PRIOR_ART_HEADER, *lines]))
