"""Engine-owned git worktree lifecycle (roadmap §9 — Worktree Phase 1).

Real git repos in tmp_path, no mocks: spawn/reconcile shell out to git, so these
tests assert on actual worktrees, branches, and registry state. The acceptance bar
is the roadmap's: `git worktree list` is clean after every scenario, including a
simulated mid-run kill recovered purely from the `.pqa/state.json` registry.

The registry shares `.pqa/state.json` with the run journal (pqa.state) — both
writers must preserve the other's keys; that contract is pinned here too.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pqa.state import load_journal, record_stage
from pqa.worktrees import (
    WorktreeError,
    reconcile,
    registered,
    spawn,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return res.stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    _git(tmp_path, "config", "user.email", "pqa@test.local")
    _git(tmp_path, "config", "user.name", "PQA Tests")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _worktree_paths(repo: Path) -> list[str]:
    out = _git(repo, "worktree", "list", "--porcelain")
    return [line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("worktree ")]


def _pqa_branches(repo: Path) -> list[str]:
    out = _git(repo, "branch", "--list", "pqa/*", "--format=%(refname:short)")
    return [b for b in out.splitlines() if b]


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)


# ---------------------------------------------------------------------------
# spawn


def test_spawn_creates_n_worktrees_on_pqa_branches(repo: Path):
    trees = spawn("run1", 3, repo_root=repo)
    assert [w.branch for w in trees] == ["pqa/run1-b1", "pqa/run1-b2", "pqa/run1-b3"]
    assert [w.index for w in trees] == [1, 2, 3]
    assert [w.run_id for w in trees] == ["run1", "run1", "run1"]
    for w in trees:
        tree = repo / w.path
        assert tree.is_dir()
        # Each worktree is a checkout of HEAD, ready for a generator to write into.
        assert (tree / "README.md").read_text(encoding="utf-8") == "base\n"
    assert len(_worktree_paths(repo)) == 4  # main + 3 branches
    assert _pqa_branches(repo) == [w.branch for w in trees]


def test_spawn_paths_are_repo_relative(repo: Path):
    trees = spawn("run1", 2, repo_root=repo)
    assert [w.path for w in trees] == [
        ".pqa_worktrees/run1-b1",
        ".pqa_worktrees/run1-b2",
    ]


def test_spawn_records_registry_in_state_json(repo: Path):
    spawn("run1", 2, repo_root=repo)
    raw = json.loads((repo / ".pqa" / "state.json").read_text(encoding="utf-8"))
    entries = raw["worktrees"]["run1"]
    assert [e["branch"] for e in entries] == ["pqa/run1-b1", "pqa/run1-b2"]
    assert [e["path"] for e in entries] == [
        ".pqa_worktrees/run1-b1",
        ".pqa_worktrees/run1-b2",
    ]


def test_spawn_partial_failure_rolls_back_everything_it_created(repo: Path):
    # Pre-existing branch makes `git worktree add -b` fail at i=2: the rollback
    # must remove what THIS call created and nothing else (trap semantics).
    _git(repo, "branch", "pqa/run1-b2")
    with pytest.raises(WorktreeError):
        spawn("run1", 3, repo_root=repo)
    assert _pqa_branches(repo) == ["pqa/run1-b2"]  # the pre-existing one, untouched
    assert not (repo / ".pqa_worktrees" / "run1-b1").exists()
    assert len(_worktree_paths(repo)) == 1
    assert registered(repo_root=repo) == {}


@pytest.mark.parametrize("bad", ["", "has space", "a/b", "-leading-dash", "../up"])
def test_spawn_rejects_unsafe_run_ids(repo: Path, bad: str):
    with pytest.raises(ValueError):
        spawn(bad, 2, repo_root=repo)
    assert _pqa_branches(repo) == []


def test_spawn_rejects_non_positive_n(repo: Path):
    with pytest.raises(ValueError):
        spawn("run1", 0, repo_root=repo)


# ---------------------------------------------------------------------------
# registry coexistence with the run journal (shared .pqa/state.json)


def test_spawn_preserves_run_journal_in_shared_state_file(repo: Path):
    state = repo / ".pqa" / "state.json"
    record_stage(state, "s1", "task", "frame", spend_tokens=10)
    spawn("run1", 2, repo_root=repo)
    journal = load_journal(state)
    assert journal is not None and journal.completed() == ("frame",)


def test_record_stage_preserves_worktree_registry(repo: Path):
    state = repo / ".pqa" / "state.json"
    spawn("run1", 2, repo_root=repo)
    record_stage(state, "s1", "task", "superpose", spend_tokens=10)
    runs = registered(repo_root=repo)
    assert "run1" in runs and len(runs["run1"]) == 2


def test_registered_round_trips_worktrees(repo: Path):
    spawned = spawn("run1", 2, repo_root=repo)
    runs = registered(repo_root=repo)
    assert list(runs.keys()) == ["run1"]
    assert list(runs["run1"]) == spawned


def test_registered_is_empty_without_registry(repo: Path):
    assert registered(repo_root=repo) == {}


def test_registered_returns_empty_on_corrupt_state_file(repo: Path):
    state = repo / ".pqa" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{not json", encoding="utf-8")
    assert registered(repo_root=repo) == {}


def test_registered_skips_malformed_entries(repo: Path):
    state = repo / ".pqa" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "worktrees": {
                    "run1": [
                        {"index": 1, "branch": "pqa/run1-b1", "path": ".pqa_worktrees/run1-b1"},
                        {"branch": "missing index and path"},
                        "not even a dict",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    runs = registered(repo_root=repo)
    assert [w.branch for w in runs["run1"]] == ["pqa/run1-b1"]


# ---------------------------------------------------------------------------
# reconcile


def test_reconcile_merges_survivor_no_ff_and_prunes(repo: Path):
    trees = spawn("run1", 2, repo_root=repo)
    wt = repo / trees[0].path
    (wt / "win.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(wt, "branch work")
    result = reconcile("run1", trees[0].branch, repo_root=repo)
    assert result.merged is True
    assert result.merge_failed is False
    assert result.preserved_branch is None
    # --no-ff: HEAD is a merge commit with two parents and the survivor's work landed.
    assert len(_git(repo, "log", "-1", "--pretty=%P").split()) == 2
    assert (repo / "win.py").exists()
    assert _pqa_branches(repo) == []
    assert len(_worktree_paths(repo)) == 1
    assert registered(repo_root=repo) == {}


def test_reconcile_conflict_aborts_preserves_survivor_still_prunes(repo: Path):
    trees = spawn("run1", 1, repo_root=repo)
    (repo / "README.md").write_text("main change\n", encoding="utf-8")
    _commit_all(repo, "main moves on")
    wt = repo / trees[0].path
    (wt / "README.md").write_text("branch change\n", encoding="utf-8")
    _commit_all(wt, "conflicting branch work")
    result = reconcile("run1", trees[0].branch, repo_root=repo)
    assert result.merged is False
    assert result.merge_failed is True
    assert result.preserved_branch == "pqa/run1-b1"
    # Never left mid-merge; main's content intact; survivor's commits still reachable.
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    assert (repo / "README.md").read_text(encoding="utf-8") == "main change\n"
    assert _pqa_branches(repo) == ["pqa/run1-b1"]
    assert len(_worktree_paths(repo)) == 1  # trees are still pruned
    assert registered(repo_root=repo) == {}


def test_reconcile_without_survivor_just_cleans(repo: Path):
    spawn("run1", 2, repo_root=repo)
    result = reconcile("run1", None, repo_root=repo)
    assert result.merged is False
    assert result.merge_failed is False
    assert len(result.removed_trees) == 2
    assert len(result.deleted_branches) == 2
    assert _pqa_branches(repo) == []
    assert len(_worktree_paths(repo)) == 1
    assert registered(repo_root=repo) == {}


def test_reconcile_is_idempotent(repo: Path):
    spawn("run1", 2, repo_root=repo)
    reconcile("run1", None, repo_root=repo)
    again = reconcile("run1", None, repo_root=repo)
    assert again.removed_trees == ()
    assert again.deleted_branches == ()
    assert len(_worktree_paths(repo)) == 1


def test_reconcile_unknown_survivor_reports_failure_and_cleans(repo: Path):
    spawn("run1", 1, repo_root=repo)
    result = reconcile("run1", "pqa/does-not-exist", repo_root=repo)
    assert result.merged is False
    assert result.merge_failed is True
    assert len(_worktree_paths(repo)) == 1
    assert registered(repo_root=repo) == {}


def test_reconcile_only_touches_its_own_run(repo: Path):
    spawn("run1", 1, repo_root=repo)
    other = spawn("run2", 1, repo_root=repo)
    reconcile("run1", None, repo_root=repo)
    assert _pqa_branches(repo) == ["pqa/run2-b1"]
    assert (repo / other[0].path).is_dir()
    assert list(registered(repo_root=repo).keys()) == ["run2"]


# ---------------------------------------------------------------------------
# mid-run kill: the registry is the recovery path (roadmap §9 acceptance)


def test_mid_run_kill_leaves_zero_orphans_after_registry_recovery(repo: Path):
    spawn("run1", 3, repo_root=repo)
    # Simulate the orchestrator dying here: no cleanup ran, and the crash even
    # corrupted one tree. A fresh process discovers the run purely from the
    # registry and reconciles with no survivor.
    shutil.rmtree(repo / ".pqa_worktrees" / "run1-b2")
    strays = registered(repo_root=repo)
    assert "run1" in strays
    reconcile("run1", None, repo_root=repo)
    assert len(_worktree_paths(repo)) == 1  # git worktree list is clean
    assert _pqa_branches(repo) == []  # zero pqa/* branches
    assert registered(repo_root=repo) == {}


# ---------------------------------------------------------------------------
# shell scripts are thin callers of the engine (roadmap §9.1)


def test_spawn_script_is_a_thin_engine_caller(repo: Path):
    script = REPO_ROOT / "scripts" / "spawn_branches.sh"
    res = subprocess.run(
        ["bash", str(script), "runS", "2"], cwd=repo, capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == [
        ".pqa_worktrees/runS-b1",
        ".pqa_worktrees/runS-b2",
    ]
    # The engine wrote the registry — proof the script went through pqa.worktrees.
    assert "runS" in registered(repo_root=repo)


def test_reconcile_script_cleans_and_reports(repo: Path):
    spawn("runS", 2, repo_root=repo)
    script = REPO_ROOT / "scripts" / "reconcile.sh"
    res = subprocess.run(["bash", str(script), "runS"], cwd=repo, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "reconciled run runS" in res.stdout
    assert registered(repo_root=repo) == {}
    assert len(_worktree_paths(repo)) == 1


def test_reconcile_script_exits_nonzero_on_merge_failure(repo: Path):
    spawn("runS", 1, repo_root=repo)
    script = REPO_ROOT / "scripts" / "reconcile.sh"
    res = subprocess.run(
        ["bash", str(script), "runS", "pqa/does-not-exist"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "merge pqa/does-not-exist manually" in res.stderr
    assert len(_worktree_paths(repo)) == 1
