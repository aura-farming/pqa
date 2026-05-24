"""Schema migration runner: versioned, gap-free, idempotent SQLite upgrades.

PQA's memory schema evolves — new tables, new columns, new indexes — and operators
running a previous release need a clean upgrade path. This module is the runner.

Migrations live in `hooks/memory/migrations/NNN_<description>.sql` — numbered from
001, gap-free, applied exactly once. Each migration runs in its own transaction:
either every statement in it commits, or the migration leaves no trace and the
schema_version row is not written. The runner is idempotent — re-running it on an
up-to-date database does nothing.

Closes Gap #12 from the plan.
"""

from __future__ import annotations

import itertools
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_FILENAME = re.compile(r"^(\d{3})_(\w+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    path: Path


def discover_migrations(migrations_dir: Path) -> list[Migration]:
    """Read every NNN_description.sql file from the directory, sorted by version.
    Rejects gaps, duplicates, and a non-1 starting version — the schema must form an
    unbroken sequence."""
    if not migrations_dir.exists():
        raise FileNotFoundError(migrations_dir)

    found: dict[int, Migration] = {}
    for entry in sorted(migrations_dir.iterdir()):
        if not entry.is_file():
            continue
        match = _FILENAME.match(entry.name)
        if not match:
            continue
        version = int(match.group(1))
        name = match.group(2)
        if version in found:
            raise ValueError(
                f"duplicate migration version {version}: "
                f"{found[version].path.name} and {entry.name}"
            )
        found[version] = Migration(
            version=version,
            name=name,
            sql=entry.read_text(),
            path=entry,
        )

    if not found:
        return []

    versions = sorted(found)
    if versions[0] != 1:
        raise ValueError(f"migrations must start at version 1, lowest found is {versions[0]}")
    for prev, curr in itertools.pairwise(versions):
        if curr != prev + 1:
            raise ValueError(f"migration gap: jumped from version {prev} to {curr}")

    return [found[v] for v in versions]


def ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    """Idempotently create the table that tracks applied migrations."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version    INTEGER PRIMARY KEY,"
        "  applied_at INTEGER NOT NULL"
        ")"
    )
    conn.commit()


def current_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or 0 if none have been applied
    (including the case where the schema_version table does not exist yet)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    result = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(result[0]) if result and result[0] is not None else 0


def _split_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL script into individual statements using SQLite's own
    statement-completeness checker. We cannot use conn.executescript() because that API
    documents itself as ignoring transaction state and silently committing — which makes
    "roll back a failed migration" impossible."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            trimmed = buffer.strip()
            if trimmed:
                statements.append(trimmed)
            buffer = ""
    tail = buffer.strip()
    if tail:
        statements.append(tail)
    return statements


def apply_migrations(conn: sqlite3.Connection, migrations: list[Migration]) -> list[int]:
    """Apply every migration whose version is greater than the current applied version,
    in numeric order. Each migration runs inside an explicit transaction — if the SQL
    raises, the transaction is rolled back and the schema_version row is NOT written.

    Returns the list of versions actually applied this call (empty when the DB is
    already up to date)."""
    ensure_schema_version_table(conn)
    applied_so_far = current_version(conn)

    pending = [m for m in migrations if m.version > applied_so_far]
    if not pending:
        return []

    applied: list[int] = []
    for migration in pending:
        try:
            conn.execute("BEGIN")
            for stmt in _split_statements(migration.sql):
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
                (migration.version, int(time.time())),
            )
            conn.commit()
            applied.append(migration.version)
        except sqlite3.Error:
            conn.rollback()
            raise

    return applied
