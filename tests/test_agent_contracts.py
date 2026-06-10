"""Contract tests for the hand-written plugin surface (roadmap §4.1 acceptance).

The orchestrator agent is the context-discipline keystone. These tests pin the exact
regressions the roadmap names — branch-payload interpolation into adversary/judge
prompts, opus-pinning, the per-agent CLAUDE.md tax — and protect the hand-written
files from being clobbered by the component generator until Phase 3a inverts it
into a validator.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from pqa.state import STAGES

REPO = Path(__file__).resolve().parent.parent
ORCHESTRATOR = REPO / "agents" / "pqa-orchestrator.md"
PQA_COMMAND = REPO / "commands" / "pqa.md"


@pytest.fixture(scope="module")
def orchestrator() -> str:
    return ORCHESTRATOR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pqa_command() -> str:
    return PQA_COMMAND.read_text(encoding="utf-8")


def test_orchestrator_never_interpolates_branch_payloads(orchestrator: str):
    # The two mega-prompt interpolations roadmap §4.1 calls out: full branch code
    # in the adversary prompt and full branch state in the judge prompt.
    assert "${BRANCH_OUTPUTS}" not in orchestrator
    assert "${BRANCH_STATE_JSON}" not in orchestrator


def test_orchestrator_dispatches_adversary_per_branch_by_path(orchestrator: str):
    assert ".pqa/branches/b" in orchestrator
    assert "Read the code yourself" in orchestrator


def test_orchestrator_runs_on_sonnet_with_opus_reserved_for_judgment(orchestrator: str):
    frontmatter = orchestrator.split("---")[1]
    assert "model: sonnet" in frontmatter
    assert 'model="opus"' in orchestrator  # adversary dispatch stays judgment-grade


def test_orchestrator_does_not_load_claude_md(orchestrator: str):
    # §4.2.4: the 60-token loop contract is inlined; the ~1k-word file is never loaded.
    assert "do not load CLAUDE.md" in orchestrator


def test_orchestrator_journals_every_canonical_stage(orchestrator: str):
    for stage in STAGES:
        assert stage in orchestrator, f"stage {stage!r} missing from the agent"
    assert ".pqa/state.json" in orchestrator
    assert "record_stage" in orchestrator


def test_orchestrator_caps_generator_digests(orchestrator: str):
    assert "150 tokens" in orchestrator


def test_orchestrator_kills_statically_broken_branches_before_adversary(orchestrator: str):
    assert "early-kill" in orchestrator.lower()


def test_orchestrator_queries_prior_art_at_frame_load(orchestrator: str):
    assert "prior_art" in orchestrator
    assert "memories_injected" in orchestrator


def test_pqa_command_wires_resume(pqa_command: str):
    assert "--resume" in pqa_command
    assert ".pqa/state.json" in pqa_command


def test_pqa_command_defers_loop_to_the_orchestrator(pqa_command: str):
    assert "pqa-orchestrator" in pqa_command


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_components", REPO / "scripts" / "generate_components.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_never_overwrites_handwritten_components(tmp_path: Path, monkeypatch):
    """Until Phase 3a inverts the generator into a validator, it must refuse to
    stamp its template over components that graduated to hand-written."""
    gen = _load_generator()
    for sub in ("agents", "commands", "skills", "docs"):
        (tmp_path / sub).mkdir()
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    gen.write_all()
    assert not (tmp_path / "agents" / "pqa-orchestrator.md").exists()
    assert not (tmp_path / "commands" / "pqa.md").exists()
    # ...while still generating everything that has not graduated yet.
    assert (tmp_path / "agents" / "pqa-adversary.md").exists()
