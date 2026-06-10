"""Run journal — crash-resumable stage completion for `/pqa --resume`.

The most expensive failure mode a harness can have is a 10-dispatch loop dying at
dispatch 8 and restarting from zero (roadmap §5.4). The journal makes every stage
completion durable the moment it happens: one JSON file under `.pqa/`, written
tmp-then-rename so a reader (or a crash) never sees a torn state. `resume_point()`
then names the first incomplete stage so the orchestrator re-enters exactly where
the run died instead of re-spending everything before it.

Spend figures are cumulative snapshots at the moment each stage completed, not
per-stage deltas — resume needs "how much was already spent", not an itemised bill.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

_JOURNAL_VERSION = 1

# The canonical loop, in order. Callers journaling finer-grained work (e.g. one
# entry per adversary attack) may use their own stage names and pipeline.
STAGES: tuple[str, ...] = (
    "frame",
    "superpose",
    "collide",
    "verify",
    "collapse",
    "precipitate",
    "report",
)


class JournalError(ValueError):
    """The journal file exists but cannot be trusted: corrupt JSON, missing fields,
    or a version this build does not understand."""


@dataclass(frozen=True)
class StageRecord:
    stage: str
    completed_at: int
    artifacts: tuple[str, ...] = ()
    spend_usd: float = 0.0
    spend_tokens: int = 0


@dataclass(frozen=True)
class RunJournal:
    session_id: str
    task: str
    stages: tuple[StageRecord, ...] = ()

    def completed(self) -> tuple[str, ...]:
        return tuple(record.stage for record in self.stages)


def load_journal(path: str | Path) -> RunJournal | None:
    """Read the journal at `path`. Returns None when no journal exists (a fresh run);
    raises JournalError when one exists but cannot be parsed — whether to start over
    is the caller's decision, never this module's."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JournalError(f"unreadable run journal at {p}: {exc}") from exc
    return _parse(raw, p)


def _parse(raw: object, p: Path) -> RunJournal:
    if not isinstance(raw, dict):
        raise JournalError(f"run journal at {p} is not a JSON object")
    data = cast(dict[str, Any], raw)
    if data.get("version") != _JOURNAL_VERSION:
        raise JournalError(
            f"run journal at {p} has version {data.get('version')!r}; "
            f"this build understands version {_JOURNAL_VERSION}"
        )
    session_id, task, stages_raw = data.get("session_id"), data.get("task"), data.get("stages")
    if not isinstance(session_id, str) or not isinstance(task, str):
        raise JournalError(f"run journal at {p} is missing session_id/task")
    if not isinstance(stages_raw, list):
        raise JournalError(f"run journal at {p} has a non-list stages field")
    try:
        stages = tuple(_parse_stage(entry) for entry in cast(list[Any], stages_raw))
    except (TypeError, KeyError, ValueError) as exc:
        raise JournalError(f"run journal at {p} has a malformed stage record: {exc}") from exc
    return RunJournal(session_id=session_id, task=task, stages=stages)


def _parse_stage(entry: object) -> StageRecord:
    if not isinstance(entry, dict):
        raise TypeError(f"stage record must be an object, got {type(entry).__name__}")
    record = cast(dict[str, Any], entry)
    return StageRecord(
        stage=str(record["stage"]),
        completed_at=int(record["completed_at"]),
        artifacts=tuple(str(a) for a in record.get("artifacts", [])),
        spend_usd=float(record.get("spend_usd", 0.0)),
        spend_tokens=int(record.get("spend_tokens", 0)),
    )


def record_stage(
    path: str | Path,
    session_id: str,
    task: str,
    stage: str,
    *,
    artifacts: Sequence[str] = (),
    spend_usd: float = 0.0,
    spend_tokens: int = 0,
) -> RunJournal:
    """Durably mark `stage` complete and return the new journal. The write is atomic
    (tmp + rename, the update_check pattern). Re-recording a stage replaces its entry;
    a different session_id supersedes the whole journal — one file tracks exactly one
    run. A corrupt predecessor file is also superseded: the live run must never be
    blocked by a stale artifact (the resume *reader* still surfaces corruption loudly)."""
    if not stage:
        raise ValueError("stage name must be non-empty")
    p = Path(path)
    try:
        existing = load_journal(p)
    except JournalError:
        existing = None
    if existing is None or existing.session_id != session_id:
        existing = RunJournal(session_id=session_id, task=task, stages=())
    record = StageRecord(
        stage=stage,
        completed_at=int(time.time()),
        artifacts=tuple(artifacts),
        spend_usd=spend_usd,
        spend_tokens=spend_tokens,
    )
    kept = tuple(s for s in existing.stages if s.stage != stage)
    journal = RunJournal(session_id=session_id, task=task, stages=(*kept, record))
    _write_atomic(p, journal)
    return journal


def resume_point(journal: RunJournal, pipeline: Sequence[str] = STAGES) -> str | None:
    """The first stage of `pipeline` the journal has not recorded as complete —
    where `/pqa --resume` re-enters. None means the run finished every stage."""
    done = set(journal.completed())
    return next((stage for stage in pipeline if stage not in done), None)


def _write_atomic(p: Path, journal: RunJournal) -> None:
    payload = {
        "version": _JOURNAL_VERSION,
        "session_id": journal.session_id,
        "task": journal.task,
        "stages": [asdict(record) for record in journal.stages],
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(p)
