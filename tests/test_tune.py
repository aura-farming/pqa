"""Tests for scripts/tune.py — config proposals from real run telemetry.

`/tune` was a stub agent; roadmap §5.3 said implement-or-cut. The cut half removed
the command; this is the implement half: a deterministic script that refuses to
propose anything until it has seen enough runs, then suggests config diffs it can
defend from the data.
"""

import importlib.util
import sqlite3
import time
from pathlib import Path
from types import ModuleType

from pqa.config import load_or_defaults
from pqa.memory import connect

REPO = Path(__file__).resolve().parent.parent


def _load_tune() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tune", REPO / "scripts" / "tune.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_runs(conn: sqlite3.Connection, n: int, *, cost: float, status: str) -> None:
    for i in range(n):
        conn.execute(
            "INSERT INTO cost_runs(session_id, task, total_cost, budget_usd, status,"
            " branches, created_at) VALUES(?,?,?,?,?,?,?)",
            (f"s{i}-{status}", "t", cost, 5.0, status, 3, int(time.time())),
        )
    conn.commit()


def test_tune_refuses_below_ten_runs(tmp_path: Path):
    tune = _load_tune()
    conn = connect(tmp_path / "m.db")
    _seed_runs(conn, 4, cost=1.0, status="ok")
    out = tune.proposals(conn, load_or_defaults(tmp_path / "none.toml"))
    assert len(out) == 1 and "insufficient" in out[0]


def test_tune_proposes_budget_raise_on_abort_heavy_history(tmp_path: Path):
    tune = _load_tune()
    conn = connect(tmp_path / "m.db")
    _seed_runs(conn, 6, cost=5.0, status="abort")
    _seed_runs(conn, 6, cost=3.0, status="ok")
    out = tune.proposals(conn, load_or_defaults(tmp_path / "none.toml"))
    assert any("abort" in p for p in out)


def test_tune_proposes_tightening_when_budget_is_slack(tmp_path: Path):
    tune = _load_tune()
    conn = connect(tmp_path / "m.db")
    _seed_runs(conn, 12, cost=0.4, status="ok")  # never near the 5.0 cap
    out = tune.proposals(conn, load_or_defaults(tmp_path / "none.toml"))
    assert any("run_budget_usd" in p for p in out)


def test_tune_never_edits_config_itself(tmp_path: Path):
    """tune proposes; the operator decides. There must be no write path to config."""
    source = (REPO / "scripts" / "tune.py").read_text(encoding="utf-8")
    assert "write_text" not in source
    assert ".write(" not in source
