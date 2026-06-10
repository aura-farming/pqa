"""Engine-owned git worktree lifecycle — Worktree Phase 1 (roadmap §9).

One isolated git worktree per superposition branch: `spawn` creates N trees on
ephemeral `pqa/<run>-bN` branches with a write-ahead registry in `.pqa/state.json`,
`reconcile` merges the survivor `--no-ff` and always prunes, and `registered` lets
a fresh process find strays after a mid-run kill. The semantics mirror the original
scripts/spawn_branches.sh trap + reconcile.sh flow; those scripts are now thin
callers of this module.

Failure discipline: a partial spawn never orphans trees (rollback removes
everything the call created, then raises), and reconcile cleans up even when the
merge conflicts (abort, preserve the survivor branch for a manual merge, prune the
rest). The registry is written BEFORE the first git mutation, so a SIGKILL at any
point still leaves the strays findable — the shell trap could never survive that.

The registry shares `.pqa/state.json` with the run journal (pqa.state); each writer
preserves the other's top-level keys. Single-writer assumption: the orchestrator
serialises journal and registry writes, so no cross-process locking here.

This module must import under bare system python3 (pre-3.10) as well as the uv
toolchain — the shell thin-callers use whatever python3 is on PATH. Hence stdlib
only, no `slots=True`, no runtime union syntax.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

WORKTREE_ROOT = ".pqa_worktrees"
STATE_FILE = ".pqa/state.json"  # joined via pathlib `/`, portable as-is
_REGISTRY_KEY = "worktrees"
# Run ids and refs are interpolated into git argv: no whitespace or separators that
# could change the path shape, and no leading '-' that git would parse as a flag.
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


class WorktreeError(RuntimeError):
    """A git-level worktree operation failed. When `spawn` raises this, every tree
    and branch the call created has already been rolled back."""


@dataclass(frozen=True)
class Worktree:
    """One ephemeral branch workspace: `branch` is machine-managed (`pqa/<run>-bN`),
    `path` is repo-relative so the registry survives a repo move."""

    run_id: str
    index: int
    branch: str
    path: str


@dataclass(frozen=True)
class ReconcileResult:
    """What reconcile did. `merge_failed=True` means the merge was aborted and the
    survivor branch was preserved for a manual merge — cleanup still ran in full."""

    run_id: str
    merged: bool
    merge_failed: bool
    removed_trees: tuple[str, ...]
    deleted_branches: tuple[str, ...]
    preserved_branch: str | None


def spawn(run_id: str, n: int, *, repo_root: str | Path = ".") -> list[Worktree]:
    """Create `n` worktrees on `pqa/<run_id>-bN` branches at HEAD.

    The full plan is registered in `.pqa/state.json` before the first git mutation
    (write-ahead), so a kill at any point leaves the strays findable via
    `registered()`. On any git failure the call rolls back every tree and branch it
    created, drops the registry entry, and raises WorktreeError.
    """
    _validate_run_id(run_id)
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    root = Path(repo_root)
    plan = [_worktree_for(run_id, i) for i in range(1, n + 1)]
    _registry_put(root, run_id, plan)
    created: list[Worktree] = []
    for tree in plan:
        result = _git(root, "worktree", "add", "-b", tree.branch, tree.path, "HEAD")
        if result.returncode != 0:
            _rollback(root, run_id, created)
            raise WorktreeError(
                f"spawn failed for {tree.branch}: {result.stderr.strip()} — "
                f"rolled back {len(created)} partial worktree(s)"
            )
        created.append(tree)
    return created


def reconcile(
    run_id: str,
    survivor: str | None = None,
    *,
    repo_root: str | Path = ".",
) -> ReconcileResult:
    """Merge the survivor `--no-ff` (when given), then ALWAYS prune this run's
    trees and branches — even when the merge conflicts (aborted; the survivor
    branch is preserved for a manual merge and reported on the result).

    Idempotent: reconciling an already-clean run is a no-op. Strays are collected
    from the registry AND the worktree directory AND `git branch --list`, so
    recovery works whichever artifacts a crash left behind.
    """
    _validate_run_id(run_id)
    if survivor is not None and not _REF_RE.fullmatch(survivor):
        raise ValueError(f"unsafe survivor ref {survivor!r}")
    root = Path(repo_root)
    merged, merge_failed = _merge_survivor(root, survivor)
    preserved = survivor if merge_failed else None
    removed = _remove_trees(root, run_id)
    deleted = _delete_branches(root, run_id, keep=preserved)
    _registry_drop(root, run_id)
    return ReconcileResult(
        run_id=run_id,
        merged=merged,
        merge_failed=merge_failed,
        removed_trees=tuple(removed),
        deleted_branches=tuple(deleted),
        preserved_branch=preserved,
    )


def registered(*, repo_root: str | Path = ".") -> dict[str, tuple[Worktree, ...]]:
    """Every run with registry entries — how a fresh process finds strays after a
    crash. Returns {} when there is no registry and skips malformed entries; the
    recovery path must never be blocked by a corrupt file."""
    registry = _read_state(Path(repo_root)).get(_REGISTRY_KEY)
    if not isinstance(registry, dict):
        return {}
    runs: dict[str, tuple[Worktree, ...]] = {}
    for run_id, entries in cast("dict[str, Any]", registry).items():
        if not isinstance(entries, list):
            continue
        parsed = (_parse_entry(str(run_id), e) for e in cast("list[Any]", entries))
        runs[str(run_id)] = tuple(tree for tree in parsed if tree is not None)
    return runs


# ---------------------------------------------------------------------------
# git plumbing


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # S603/S607: argv is the fixed `git` executable (resolved from PATH on purpose —
    # an absolute path would break across hosts) plus engine-constructed args; run
    # ids and survivor refs are validated against the allowlist regexes above.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )


def _worktree_for(run_id: str, index: int) -> Worktree:
    return Worktree(
        run_id=run_id,
        index=index,
        branch=f"pqa/{run_id}-b{index}",
        path=f"{WORKTREE_ROOT}/{run_id}-b{index}",
    )


def _rollback(root: Path, run_id: str, created: list[Worktree]) -> None:
    """Mirror the spawn_branches.sh trap: remove every tree+branch THIS call
    created (never pre-existing ones), prune, drop the registry entry. Best-effort
    per item — rollback must always run to completion."""
    for tree in created:
        _git(root, "worktree", "remove", "--force", tree.path)
    _git(root, "worktree", "prune")
    for tree in created:
        _git(root, "branch", "-D", tree.branch)
    _registry_drop(root, run_id)


def _merge_survivor(root: Path, survivor: str | None) -> tuple[bool, bool]:
    """(merged, merge_failed). On failure the merge is aborted so the repo is never
    left mid-merge; the caller preserves the survivor branch for a manual merge."""
    if not survivor:
        return False, False
    message = f"feat: merge PQA survivor {survivor}"
    result = _git(root, "merge", "--no-ff", survivor, "-m", message)
    if result.returncode == 0:
        return True, False
    _git(root, "merge", "--abort")  # best-effort: there may be no merge to abort
    return False, True


def _remove_trees(root: Path, run_id: str) -> list[str]:
    """Remove this run's worktrees: union of registry paths and on-disk
    `.pqa_worktrees/<run>-b*`, then prune so git forgets even trees a crash
    already deleted from disk."""
    candidates = {tree.path for tree in registered(repo_root=root).get(run_id, ())}
    worktree_dir = root / WORKTREE_ROOT
    if worktree_dir.is_dir():
        for entry in worktree_dir.glob(f"{run_id}-b*"):
            candidates.add(f"{WORKTREE_ROOT}/{entry.name}")
    removed: list[str] = []
    for path in sorted(candidates):
        if not (root / path).exists():
            continue  # crash already deleted the tree; prune clears git's record
        if _git(root, "worktree", "remove", "--force", path).returncode == 0:
            removed.append(path)
    _git(root, "worktree", "prune")
    return removed


def _delete_branches(root: Path, run_id: str, keep: str | None) -> list[str]:
    listing = _git(root, "branch", "--list", f"pqa/{run_id}-b*", "--format=%(refname:short)")
    deleted: list[str] = []
    for branch in (line for line in listing.stdout.splitlines() if line):
        if keep is not None and branch == keep:
            continue  # an unmerged survivor's commits must stay reachable
        if _git(root, "branch", "-D", branch).returncode == 0:
            deleted.append(branch)
    return deleted


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            f"unsafe run id {run_id!r}: use [A-Za-z0-9._-] with a leading alphanumeric"
        )


# ---------------------------------------------------------------------------
# registry I/O — shares .pqa/state.json with the run journal (pqa.state)


def _read_state(root: Path) -> dict[str, Any]:
    path = root / STATE_FILE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}
    return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}


def _write_state(root: Path, state: dict[str, Any]) -> None:
    path = root / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


def _registry_put(root: Path, run_id: str, plan: list[Worktree]) -> None:
    state = _read_state(root)
    registry = state.get(_REGISTRY_KEY)
    table: dict[str, Any] = (
        dict(cast("dict[str, Any]", registry)) if isinstance(registry, dict) else {}
    )
    table[run_id] = [
        {"index": tree.index, "branch": tree.branch, "path": tree.path} for tree in plan
    ]
    _write_state(root, {**state, _REGISTRY_KEY: table})


def _registry_drop(root: Path, run_id: str) -> None:
    state = _read_state(root)
    registry = state.get(_REGISTRY_KEY)
    if not isinstance(registry, dict) or run_id not in registry:
        return
    table = {k: v for k, v in cast("dict[str, Any]", registry).items() if k != run_id}
    _write_state(root, {**state, _REGISTRY_KEY: table})


def _parse_entry(run_id: str, entry: object) -> Worktree | None:
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, Any]", entry)
    try:
        return Worktree(
            run_id=run_id,
            index=int(record["index"]),
            branch=str(record["branch"]),
            path=str(record["path"]),
        )
    except KeyError, TypeError, ValueError:
        return None
