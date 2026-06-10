#!/usr/bin/env python3
"""PQA eval harness — score solutions against locked verifiers, report PQA vs baseline.

No model calls live here (roadmap §8): agents (pqa-eval-runner driving the orchestrator
and pqa-baseline-runner) produce solution files; this script is the deterministic
measurement. It loads the task set, runs each task's LOCKED verifier in a subprocess,
accumulates score rows, and emits the honest results JSON — losses first.

Usage:
  python3 scripts/eval_harness.py list
  python3 scripts/eval_harness.py score <task> <solution.py> --arm pqa|baseline
         [--tokens N] [--unverified]
  python3 scripts/eval_harness.py report <YYYY-MM-DD>
  python3 scripts/eval_harness.py smoke [--all]     # verifier integrity (CI)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO / "evals" / "tasks"
WORK_FILE = REPO / "evals" / "work" / "rows.jsonl"
RESULTS_DIR = REPO / "evals" / "results"
VERIFIER_TIMEOUT_S = 30
ARMS = ("pqa", "baseline")


def _parse_task_toml(text: str) -> dict[str, str]:
    """Flat `key = "value"` pairs — the entire grammar this task set uses. Parsed by
    hand so the harness runs on any python3 (no tomllib floor), like the hooks."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').replace('\\"', '"')
    return out


def load_tasks(tasks_dir: Path = TASKS_DIR) -> list[dict[str, str]]:
    """Every task.toml in the set, sorted by name. A task without a verifier is a
    broken benchmark and reported as such immediately."""
    tasks: list[dict[str, str]] = []
    for d in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        spec = _parse_task_toml((d / "task.toml").read_text(encoding="utf-8"))
        if not (d / "verify.py").exists():
            raise FileNotFoundError(f"{d.name}: missing locked verifier verify.py")
        tasks.append({"name": spec["name"], "entry": spec["entry"], "dir": str(d)})
    return tasks


def run_verifier(task_dir: Path, solution: Path) -> tuple[str, str]:
    """Run the locked verifier in a subprocess. Returns (status, detail) where status
    is pass | fail | infra_error. The verifier's exit status is the only score."""
    try:
        # S603: argv is sys.executable + repo-controlled verify.py + the solution path
        # the caller chose to score — no shell, no untrusted argv construction.
        proc = subprocess.run(  # noqa: S603
            [sys.executable, str(task_dir / "verify.py"), str(solution)],
            capture_output=True,
            text=True,
            timeout=VERIFIER_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return "infra_error", f"verifier timed out after {VERIFIER_TIMEOUT_S}s"
    detail = (proc.stdout or proc.stderr).strip()
    if proc.returncode == 0:
        return "pass", detail
    if proc.returncode == 1:
        return "fail", detail
    return "infra_error", detail


def score(
    task: str,
    solution: Path,
    arm: str,
    *,
    tokens: int = 0,
    unverified: bool = False,
    tasks_dir: Path = TASKS_DIR,
    work_file: Path = WORK_FILE,
) -> dict[str, object]:
    """Score one arm's solution for one task and append the row to the work file."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")
    task_dir = tasks_dir / task
    if not task_dir.is_dir():
        raise FileNotFoundError(f"unknown task {task!r}")
    status, detail = run_verifier(task_dir, solution)
    row: dict[str, object] = {
        "task": task,
        "arm": arm,
        "status": status,
        "detail": detail,
        "tokens": tokens,
        "unverified": unverified,
    }
    work_file.parent.mkdir(parents=True, exist_ok=True)
    with work_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def _latest_rows(work_file: Path) -> dict[tuple[str, str], dict[str, object]]:
    """Last score per (task, arm) wins — re-running an arm supersedes its old row."""
    latest: dict[tuple[str, str], dict[str, object]] = {}
    if not work_file.exists():
        return latest
    for line in work_file.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        latest[(str(row["task"]), str(row["arm"]))] = row
    return latest


def _classify(pqa: dict[str, object] | None, base: dict[str, object] | None) -> str:
    """win = PQA passed where baseline did not; loss = the reverse; tie = both same.
    Any infra_error voids the comparison — counted neither way."""
    if pqa is None or base is None:
        return "incomplete"
    if "infra_error" in (pqa["status"], base["status"]):
        return "infra_error"
    pqa_pass, base_pass = pqa["status"] == "pass", base["status"] == "pass"
    if pqa_pass and not base_pass:
        return "win"
    if base_pass and not pqa_pass:
        return "loss"
    return "tie"


def _tokens_of(row: dict[str, object]) -> int:
    """The row's token count, defensively: rows come from JSON on disk."""
    value = row.get("tokens", 0)
    return value if isinstance(value, int) else 0


def report(
    date: str,
    *,
    tasks_dir: Path = TASKS_DIR,
    work_file: Path = WORK_FILE,
    results_dir: Path = RESULTS_DIR,
) -> dict[str, object]:
    """Aggregate the latest rows into evals/results/<date>.json. Losses first."""
    latest = _latest_rows(work_file)
    task_rows: list[dict[str, object]] = []
    tally = {"win": 0, "loss": 0, "tie": 0, "infra_error": 0, "incomplete": 0}
    pqa_tokens = base_tokens = unverified = pqa_runs = 0
    for task in load_tasks(tasks_dir):
        pqa, base = latest.get((task["name"], "pqa")), latest.get((task["name"], "baseline"))
        verdict = _classify(pqa, base)
        tally[verdict] += 1
        if pqa is not None:
            pqa_runs += 1
            pqa_tokens += _tokens_of(pqa)
            unverified += 1 if pqa.get("unverified") else 0
        if base is not None:
            base_tokens += _tokens_of(base)
        task_rows.append(
            {
                "task": task["name"],
                "verdict": verdict,
                "pqa_pass": None if pqa is None else pqa["status"] == "pass",
                "baseline_pass": None if base is None else base["status"] == "pass",
                "pqa_tokens": None if pqa is None else pqa.get("tokens", 0),
                "baseline_tokens": None if base is None else base.get("tokens", 0),
            }
        )
    # Losses first — a results table that hides losses is marketing, not evidence.
    task_rows.sort(key=lambda r: (r["verdict"] != "loss", str(r["task"])))
    result: dict[str, object] = {
        "date": date,
        "tasks": task_rows,
        "aggregate": {
            **tally,
            "unverified_rate": round(unverified / pqa_runs, 3) if pqa_runs else 0.0,
            "cost_ratio": round(pqa_tokens / base_tokens, 2) if base_tokens else 0.0,
        },
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / f"{date}.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def smoke(*, run_all: bool = False, tasks_dir: Path = TASKS_DIR) -> int:
    """Verifier integrity: every checked task's reference must PASS its locked
    verifier and its sabotage (the planted trap) must FAIL. A verifier that cannot
    tell them apart scores nothing — this is what nightly CI runs."""
    tasks = load_tasks(tasks_dir)
    checked = tasks if run_all else tasks[:2]
    broken = 0
    for task in checked:
        d = Path(task["dir"])
        ref_status, ref_detail = run_verifier(d, d / "reference.py")
        sab_status, sab_detail = run_verifier(d, d / "sabotage.py")
        ok = ref_status == "pass" and sab_status == "fail"
        broken += 0 if ok else 1
        print(
            f"{'ok' if ok else 'BROKEN'}: {task['name']} "
            f"(reference={ref_status}, sabotage={sab_status})"
        )
        if not ok:
            print(f"  reference: {ref_detail}\n  sabotage: {sab_detail}")
    print(f"verifier integrity: {len(checked) - broken}/{len(checked)} sound")
    return 1 if broken else 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "list":
        for task in load_tasks():
            print(task["name"])
        return 0
    if cmd == "score" and len(argv) >= 4 and argv[3] == "--arm":
        tokens = int(argv[argv.index("--tokens") + 1]) if "--tokens" in argv else 0
        row = score(
            argv[1], Path(argv[2]), argv[4], tokens=tokens, unverified="--unverified" in argv
        )
        print(json.dumps(row))
        return 0 if row["status"] != "infra_error" else 2
    if cmd == "report" and len(argv) == 2:
        result = report(argv[1])
        print(json.dumps(result["aggregate"], indent=2))
        return 0
    if cmd == "smoke":
        return smoke(run_all="--all" in argv)
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
