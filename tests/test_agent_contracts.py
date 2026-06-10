"""Contract tests for the hand-written plugin surface (roadmap §4.1/§6 acceptance).

The orchestrator agent is the context-discipline keystone and the validator is what
keeps the trimmed surface disciplined. These tests pin the regressions the roadmap
names — branch-payload interpolation, model mis-routing, the per-agent CLAUDE.md tax,
catalog drift — plus the operator's 2026-06-10 directives: Fable 5 for coding and
judgment, and a scale gate so questions never trigger the full loop.
"""

import importlib.util
import json
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


def test_orchestrator_routes_fable_for_judgment_and_runs_on_sonnet(orchestrator: str):
    # Operator directive 2026-06-10: Fable 5 does the coding and quality-critical
    # judgment; the orchestrator itself is plumbing and stays on sonnet.
    frontmatter = orchestrator.split("---")[1]
    assert "model: sonnet" in frontmatter
    assert 'model="fable"' in orchestrator  # adversary dispatch
    assert "**fable**" in orchestrator  # routing table tier


def test_orchestrator_has_a_scale_gate(orchestrator: str):
    # Operator directive 2026-06-10: a compare/choose question must never trigger
    # the full multi-branch loop.
    assert "Scale gate" in orchestrator
    assert "decide" in orchestrator
    assert "Never silently upgrade" in orchestrator


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


def test_pqa_command_wires_resume_step_and_scale(pqa_command: str):
    assert "--resume" in pqa_command
    assert "--step" in pqa_command
    assert ".pqa/state.json" in pqa_command
    assert "scale gate" in pqa_command.lower()


def test_pqa_command_defers_loop_to_the_orchestrator(pqa_command: str):
    assert "pqa-orchestrator" in pqa_command


# ---------------------------------------------------------------------------
# The validator — the generator's replacement (roadmap §6.1)


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_components", REPO / "scripts" / "validate_components.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_is_gone_and_validator_exists():
    """§6.1: components are hand-written; the script that stamped them is inverted
    into a validator."""
    assert not (REPO / "scripts" / "generate_components.py").exists()
    assert (REPO / "scripts" / "validate_components.py").exists()


def test_validator_passes_on_the_shipped_tree():
    validator = _load_validator()
    violations = validator.validate(REPO)
    assert violations == [], "\n".join(violations)


def test_validator_flags_overlong_descriptions(tmp_path: Path):
    validator = _load_validator()
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "pqa-windy.md").write_text(
        "---\nname: pqa-windy\ndescription: "
        + " ".join(["word"] * 30)
        + "\ntools: Read\nmodel: sonnet\n---\nbody\n"
    )
    violations = validator.validate(tmp_path)
    assert any("description" in v and "pqa-windy" in v for v in violations)


def test_validator_flags_model_routing_drift(tmp_path: Path):
    """The routing table is enforced: an agent on the wrong tier is a violation."""
    validator = _load_validator()
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "pqa-generator.md").write_text(
        "---\nname: pqa-generator\ndescription: short enough\n"
        "tools: Read\nmodel: haiku\n---\nbody\n"
    )
    violations = validator.validate(tmp_path)
    assert any("pqa-generator" in v and "model" in v for v in violations)


def test_validator_flags_catalog_drift(tmp_path: Path):
    validator = _load_validator()
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "pqa-verifier.md").write_text(
        "---\nname: pqa-verifier\ndescription: short\ntools: Read\nmodel: sonnet\n---\nbody\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "catalog.json").write_text('{"agents": [], "commands": [], "skills": []}')
    violations = validator.validate(tmp_path)
    assert any("catalog" in v for v in violations)


def test_validator_write_catalog_regenerates_from_files(tmp_path: Path):
    validator = _load_validator()
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "pqa-verifier.md").write_text(
        "---\nname: pqa-verifier\ndescription: short\ntools: Read\nmodel: sonnet\n---\nbody\n"
    )
    (tmp_path / "docs").mkdir()
    validator.write_catalog(tmp_path)
    catalog = json.loads((tmp_path / "docs" / "catalog.json").read_text())
    assert catalog["agents"][0]["name"] == "pqa-verifier"
    assert validator.validate(tmp_path) == []
