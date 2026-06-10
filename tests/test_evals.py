"""Eval-set integrity + harness plumbing (roadmap §8, Phase 4).

The benchmark is only as honest as its verifiers: every task ships a locked verify.py,
a reference solution that must PASS it, and a sabotage solution embodying the task's
trap that must FAIL it. If a verifier cannot tell those apart, the eval proves nothing
— these tests are the lock on the lock.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO / "evals" / "tasks"
TASK_DIRS = sorted(p for p in TASKS_DIR.iterdir() if p.is_dir())


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "eval_harness", REPO / "scripts" / "eval_harness.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_benchmark_ships_eight_tasks():
    assert len(TASK_DIRS) == 8
    for d in TASK_DIRS:
        for required in ("task.toml", "verify.py", "reference.py", "sabotage.py"):
            assert (d / required).exists(), f"{d.name}: missing {required}"


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=lambda p: p.name)
def test_reference_passes_its_locked_verifier(task_dir: Path):
    harness = _load_harness()
    status, detail = harness.run_verifier(task_dir, task_dir / "reference.py")
    assert status == "pass", f"{task_dir.name} reference rejected: {detail}"


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=lambda p: p.name)
def test_sabotage_fails_its_locked_verifier(task_dir: Path):
    """The sabotage embodies the task's trap — a verifier it passes is not locked
    onto anything (and would also pass a model that fell into the trap)."""
    harness = _load_harness()
    status, detail = harness.run_verifier(task_dir, task_dir / "sabotage.py")
    assert status == "fail", f"{task_dir.name} sabotage not caught ({status}): {detail}"


def test_score_and_report_classify_wins_and_losses(tmp_path: Path):
    harness = _load_harness()
    work = tmp_path / "rows.jsonl"
    results = tmp_path / "results"
    win_task = TASK_DIRS[0]  # pqa=reference (pass), baseline=sabotage (fail) -> win
    loss_task = TASK_DIRS[1]  # the reverse -> loss
    harness.score(win_task.name, win_task / "reference.py", "pqa", tokens=40_000, work_file=work)
    harness.score(
        win_task.name, win_task / "sabotage.py", "baseline", tokens=10_000, work_file=work
    )
    harness.score(
        loss_task.name,
        loss_task / "sabotage.py",
        "pqa",
        tokens=40_000,
        unverified=True,
        work_file=work,
    )
    harness.score(
        loss_task.name, loss_task / "reference.py", "baseline", tokens=10_000, work_file=work
    )

    result = harness.report("2026-06-10", work_file=work, results_dir=results)
    agg = result["aggregate"]
    assert agg["win"] == 1
    assert agg["loss"] == 1
    assert agg["incomplete"] == 6  # the other tasks have no rows yet
    assert agg["unverified_rate"] == 0.5
    assert agg["cost_ratio"] == 4.0
    # losses first — the honesty ordering is part of the contract
    verdicts = [row["verdict"] for row in result["tasks"]]
    assert verdicts[0] == "loss"
    on_disk = json.loads((results / "2026-06-10.json").read_text())
    assert on_disk["aggregate"]["win"] == 1


def test_rescoring_supersedes_the_old_row(tmp_path: Path):
    harness = _load_harness()
    work = tmp_path / "rows.jsonl"
    task = TASK_DIRS[0]
    harness.score(task.name, task / "sabotage.py", "pqa", work_file=work)
    harness.score(task.name, task / "reference.py", "pqa", work_file=work)
    harness.score(task.name, task / "reference.py", "baseline", work_file=work)
    result = harness.report("2026-06-10", work_file=work, results_dir=tmp_path / "r")
    row = next(r for r in result["tasks"] if r["task"] == task.name)
    assert row["verdict"] == "tie"  # latest pqa row (pass) is the one that counts
    assert row["pqa_pass"] is True


def test_smoke_validates_verifier_integrity():
    harness = _load_harness()
    assert harness.smoke(run_all=True) == 0
