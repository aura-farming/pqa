"""Tests for the schema migration runner.

PQA's SQLite schema evolves (new tables, new columns, new indexes). The migration
runner gives us versioned, gap-free, idempotent upgrades so operators on earlier
releases get a clean path forward. Closes Gap #12.
"""

import sqlite3
from pathlib import Path

import pytest

from pqa.migrations import (
    Migration,
    apply_migrations,
    current_version,
    discover_migrations,
    ensure_schema_version_table,
)


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    yield conn
    conn.close()


def _write(d: Path, name: str, sql: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(sql)
    return p


# ---------------------------------------------------------------------------
# discover_migrations


def test_discover_empty_directory_returns_empty_list(tmp_path: Path):
    (tmp_path / "migrations").mkdir()
    assert discover_migrations(tmp_path / "migrations") == []


def test_discover_returns_migrations_sorted_by_version(tmp_path: Path):
    d = tmp_path / "migrations"
    _write(d, "002_add_x.sql", "CREATE TABLE x (id INTEGER);")
    _write(d, "001_initial.sql", "CREATE TABLE y (id INTEGER);")
    _write(d, "003_add_z.sql", "CREATE TABLE z (id INTEGER);")
    migrations = discover_migrations(d)
    assert [m.version for m in migrations] == [1, 2, 3]
    assert migrations[0].name == "initial"
    assert migrations[1].name == "add_x"
    assert migrations[2].name == "add_z"


def test_discover_ignores_non_migration_files(tmp_path: Path):
    d = tmp_path / "migrations"
    _write(d, "001_initial.sql", "CREATE TABLE y (id INTEGER);")
    _write(d, "README.md", "not a migration")
    _write(d, "schema.sql", "not numbered")
    migrations = discover_migrations(d)
    assert len(migrations) == 1
    assert migrations[0].version == 1


def test_discover_rejects_gaps(tmp_path: Path):
    d = tmp_path / "migrations"
    _write(d, "001_initial.sql", "CREATE TABLE y (id INTEGER);")
    _write(d, "003_skip.sql", "CREATE TABLE z (id INTEGER);")
    with pytest.raises(ValueError, match="gap"):
        discover_migrations(d)


def test_discover_rejects_duplicate_versions(tmp_path: Path):
    d = tmp_path / "migrations"
    _write(d, "001_initial.sql", "CREATE TABLE a (id INTEGER);")
    _write(d, "001_duplicate.sql", "CREATE TABLE b (id INTEGER);")
    with pytest.raises(ValueError, match="duplicate"):
        discover_migrations(d)


def test_discover_rejects_missing_directory(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        discover_migrations(tmp_path / "does-not-exist")


def test_discover_must_start_at_version_1(tmp_path: Path):
    d = tmp_path / "migrations"
    _write(d, "002_skip_initial.sql", "CREATE TABLE x (id INTEGER);")
    with pytest.raises(ValueError, match="must start at"):
        discover_migrations(d)


# ---------------------------------------------------------------------------
# current_version


def test_current_version_returns_0_on_fresh_db(db: sqlite3.Connection):
    assert current_version(db) == 0


def test_current_version_returns_highest_applied(db: sqlite3.Connection):
    ensure_schema_version_table(db)
    db.execute("INSERT INTO schema_version(version, applied_at) VALUES(1, 100)")
    db.execute("INSERT INTO schema_version(version, applied_at) VALUES(2, 200)")
    db.execute("INSERT INTO schema_version(version, applied_at) VALUES(3, 300)")
    db.commit()
    assert current_version(db) == 3


def test_current_version_with_empty_table_is_0(db: sqlite3.Connection):
    ensure_schema_version_table(db)
    assert current_version(db) == 0


# ---------------------------------------------------------------------------
# ensure_schema_version_table


def test_ensure_schema_version_table_is_idempotent(db: sqlite3.Connection):
    ensure_schema_version_table(db)
    ensure_schema_version_table(db)  # second call should not error
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "schema_version" in tables


# ---------------------------------------------------------------------------
# apply_migrations


def test_apply_migrations_runs_all_pending(db: sqlite3.Connection):
    migrations = [
        Migration(
            version=1,
            name="initial",
            sql="CREATE TABLE a (id INTEGER);",
            path=Path("001_initial.sql"),
        ),
        Migration(
            version=2,
            name="add_b",
            sql="CREATE TABLE b (id INTEGER);",
            path=Path("002_add_b.sql"),
        ),
    ]
    applied = apply_migrations(db, migrations)
    assert applied == [1, 2]
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "a" in tables
    assert "b" in tables


def test_apply_migrations_is_idempotent(db: sqlite3.Connection):
    migrations = [
        Migration(
            version=1,
            name="initial",
            sql="CREATE TABLE a (id INTEGER);",
            path=Path("001.sql"),
        ),
    ]
    applied_first = apply_migrations(db, migrations)
    applied_second = apply_migrations(db, migrations)
    assert applied_first == [1]
    assert applied_second == []  # already at version 1, nothing to do


def test_apply_migrations_skips_already_applied(db: sqlite3.Connection):
    ensure_schema_version_table(db)
    db.execute("INSERT INTO schema_version(version, applied_at) VALUES(1, 100)")
    db.commit()

    migrations = [
        Migration(
            version=1,
            name="initial",
            sql="CREATE TABLE a (id INTEGER);",
            path=Path("001.sql"),
        ),
        Migration(
            version=2,
            name="add_b",
            sql="CREATE TABLE b (id INTEGER);",
            path=Path("002.sql"),
        ),
    ]
    applied = apply_migrations(db, migrations)
    assert applied == [2]


def test_apply_migrations_rolls_back_failed(db: sqlite3.Connection):
    """A migration that errors mid-execution must not commit a partial schema and must
    not record itself in schema_version."""
    migrations = [
        Migration(
            version=1,
            name="good",
            sql="CREATE TABLE a (id INTEGER);",
            path=Path("001.sql"),
        ),
        Migration(
            version=2,
            name="bad",
            # CREATE TABLE b runs first; the second statement is invalid SQL that
            # SQLite rejects at parse time. The migration must roll back as a whole.
            sql="CREATE TABLE b (id INTEGER);\nINSERT INTO missing_table VALUES (1);",
            path=Path("002.sql"),
        ),
    ]
    with pytest.raises(sqlite3.Error):
        apply_migrations(db, migrations)

    # Version 1 applied; version 2 did not (rolled back).
    assert current_version(db) == 1

    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "a" in tables
    assert "b" not in tables  # rolled back


def test_apply_migrations_records_timestamp(db: sqlite3.Connection):
    migrations = [
        Migration(
            version=1,
            name="initial",
            sql="CREATE TABLE a (id INTEGER);",
            path=Path("001.sql"),
        ),
    ]
    apply_migrations(db, migrations)
    row = db.execute("SELECT version, applied_at FROM schema_version WHERE version = 1").fetchone()
    assert row[0] == 1
    assert row[1] > 0


def test_apply_migrations_empty_list_is_noop(db: sqlite3.Connection):
    assert apply_migrations(db, []) == []
    # Should still create the schema_version table for future use.
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "schema_version" in tables


# ---------------------------------------------------------------------------
# Migration dataclass


def test_migration_is_immutable():
    m = Migration(version=1, name="x", sql="CREATE TABLE y(id INT);", path=Path("x"))
    with pytest.raises((AttributeError, TypeError)):
        m.version = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# End-to-end


def test_real_initial_migration_creates_pqa_schema(tmp_path: Path):
    """Smoke test: applying the real 001_initial migration shipped in
    hooks/memory/migrations creates every table pqa.memory expects."""
    repo_root = Path(__file__).resolve().parent.parent
    migrations_dir = repo_root / "hooks" / "memory" / "migrations"
    if not migrations_dir.exists():
        pytest.skip("migrations directory not present in this checkout")

    migrations = discover_migrations(migrations_dir)
    assert migrations, "no migrations shipped"

    conn = sqlite3.connect(str(tmp_path / "real.db"))
    try:
        apply_migrations(conn, migrations)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        # Every table pqa.memory.connect() (and friends) writes to.
        expected = {
            "precipitates",
            "failures",
            "signals",
            "frames",
            "instincts",
            "baselines",
            "cost_runs",
            "schema_version",
        }
        assert expected <= tables
    finally:
        conn.close()
