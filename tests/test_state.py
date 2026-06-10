"""Tests for the run journal behind `/pqa --resume`.

A 10-dispatch loop that dies at dispatch 8 must not restart from zero (roadmap §5.4).
The journal records each stage completion atomically; resume_point() names the first
incomplete stage to re-enter at.
"""

from pathlib import Path

import pytest

from pqa.state import (
    STAGES,
    JournalError,
    RunJournal,
    StageRecord,
    load_journal,
    record_stage,
    resume_point,
)


def test_record_stage_creates_journal_file(tmp_path: Path):
    path = tmp_path / ".pqa" / "state.json"
    journal = record_stage(path, "s1", "build a rate limiter", "frame")
    assert path.exists()
    assert journal.session_id == "s1"
    assert journal.task == "build a rate limiter"
    assert journal.completed() == ("frame",)


def test_load_journal_roundtrips_everything(tmp_path: Path):
    path = tmp_path / "state.json"
    record_stage(path, "s1", "t", "frame", artifacts=("a.md",), spend_usd=0.5, spend_tokens=1200)
    record_stage(
        path,
        "s1",
        "t",
        "superpose",
        artifacts=(".pqa/branches/b0/", ".pqa/branches/b1/"),
        spend_usd=1.25,
        spend_tokens=40_000,
    )
    journal = load_journal(path)
    assert journal is not None
    assert journal.session_id == "s1"
    assert journal.completed() == ("frame", "superpose")
    frame, superpose = journal.stages
    assert frame.artifacts == ("a.md",)
    assert superpose.artifacts == (".pqa/branches/b0/", ".pqa/branches/b1/")
    assert superpose.spend_usd == 1.25
    assert superpose.spend_tokens == 40_000
    assert superpose.completed_at >= frame.completed_at > 0


def test_load_journal_missing_file_is_none(tmp_path: Path):
    assert load_journal(tmp_path / "absent.json") is None


def test_load_journal_corrupt_file_raises(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(JournalError):
        load_journal(p)


def test_load_journal_wrong_shape_raises(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text('{"version": 1, "session_id": "s", "task": "t", "stages": "nope"}')
    with pytest.raises(JournalError):
        load_journal(p)


def test_load_journal_unknown_version_raises(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text('{"version": 99, "session_id": "s", "task": "t", "stages": []}')
    with pytest.raises(JournalError):
        load_journal(p)


def test_load_journal_malformed_stage_raises(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text('{"version": 1, "session_id": "s", "task": "t", "stages": ["frame"]}')
    with pytest.raises(JournalError):
        load_journal(p)


def test_record_stage_is_idempotent_per_stage(tmp_path: Path):
    path = tmp_path / "state.json"
    record_stage(path, "s1", "t", "frame", spend_tokens=10)
    journal = record_stage(path, "s1", "t", "frame", spend_tokens=25)
    assert journal.completed() == ("frame",)  # replaced, not duplicated
    assert journal.stages[0].spend_tokens == 25


def test_record_stage_new_session_supersedes_old_journal(tmp_path: Path):
    path = tmp_path / "state.json"
    record_stage(path, "old-run", "t", "frame")
    record_stage(path, "old-run", "t", "superpose")
    journal = record_stage(path, "new-run", "t2", "frame")
    assert journal.session_id == "new-run"
    assert journal.completed() == ("frame",)


def test_record_stage_survives_a_corrupt_predecessor(tmp_path: Path):
    """A torn journal from a previous crash must not block the live run from
    journaling — the live run supersedes it."""
    path = tmp_path / "state.json"
    path.write_text("{torn", encoding="utf-8")
    journal = record_stage(path, "s1", "t", "frame")
    assert journal.completed() == ("frame",)
    reloaded = load_journal(path)
    assert reloaded is not None and reloaded.completed() == ("frame",)


def test_record_stage_rejects_empty_stage(tmp_path: Path):
    with pytest.raises(ValueError, match="stage"):
        record_stage(tmp_path / "state.json", "s1", "t", "")


def test_record_stage_leaves_no_tmp_files(tmp_path: Path):
    path = tmp_path / "state.json"
    record_stage(path, "s1", "t", "frame")
    record_stage(path, "s1", "t", "superpose")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []


def test_resume_point_finds_first_incomplete_stage(tmp_path: Path):
    path = tmp_path / "state.json"
    record_stage(path, "s1", "t", "frame")
    record_stage(path, "s1", "t", "superpose")
    journal = load_journal(path)
    assert journal is not None
    assert resume_point(journal) == "collide"


def test_resume_point_complete_run_is_none(tmp_path: Path):
    path = tmp_path / "state.json"
    for stage in STAGES:
        record_stage(path, "s1", "t", stage)
    journal = load_journal(path)
    assert journal is not None
    assert resume_point(journal) is None


def test_resume_point_custom_pipeline():
    journal = RunJournal(session_id="s", task="t", stages=(StageRecord(stage="a", completed_at=1),))
    assert resume_point(journal, pipeline=("a", "b")) == "b"


def test_resume_point_ignores_out_of_pipeline_stages():
    journal = RunJournal(
        session_id="s", task="t", stages=(StageRecord(stage="weird", completed_at=1),)
    )
    assert resume_point(journal, pipeline=("a",)) == "a"


def test_journal_is_immutable():
    journal = RunJournal(session_id="s", task="t", stages=())
    with pytest.raises((AttributeError, TypeError)):
        journal.session_id = "x"  # type: ignore[misc]


def test_canonical_stages_match_the_loop():
    assert STAGES == (
        "frame",
        "superpose",
        "collide",
        "verify",
        "collapse",
        "precipitate",
        "report",
    )
