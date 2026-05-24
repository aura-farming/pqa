"""Tests for the superposition layer (Phase 0: in-context branches).

Spawn N branch prompts with explicit topology guidance, hand them off to the generator
(somewhere else), then validate divergence on the populated outputs. Phase 2 will swap
the in-context branches for git worktrees behind the same interface.
"""

import pytest

from pqa.divergence import DivergenceReport
from pqa.frame import Disagreement, Frame
from pqa.superposition import (
    Branch,
    RespawnPlan,
    respawn_plan,
    spawn_prompts,
    validate_divergence,
)


def _research(content="research view") -> Frame:
    return Frame(type="research", content=content, source="docs")


def _selfeval(content="self-eval view differs") -> Frame:
    return Frame(type="selfeval", content=content, source="self-eval")


def _disagreement() -> Disagreement:
    r = _research()
    s = _selfeval()
    return Disagreement(research=r, selfeval=s, similarity=0.3, summary="real gap")


# ---------------------------------------------------------------------------
# Branch dataclass


def test_branch_is_immutable():
    b = Branch(id="b1", prompt="do x")
    with pytest.raises((AttributeError, TypeError)):
        b.output = "changed"  # type: ignore[misc]


def test_branch_defaults():
    b = Branch(id="b1", prompt="do x")
    assert b.output == ""
    assert b.conviction is None
    assert b.incremental is True


def test_branch_can_carry_conviction_and_non_incremental():
    b = Branch(id="b1", prompt="do x", conviction="high", incremental=False)
    assert b.conviction == "high"
    assert b.incremental is False


# ---------------------------------------------------------------------------
# spawn_prompts


def test_spawn_prompts_returns_n_prompts():
    prompts = spawn_prompts(3, "build a rate limiter")
    assert len(prompts) == 3


def test_spawn_prompts_n_lt_2_is_rejected():
    with pytest.raises(ValueError):
        spawn_prompts(1, "x")
    with pytest.raises(ValueError):
        spawn_prompts(0, "x")


def test_spawn_prompts_each_contains_base_prompt():
    prompts = spawn_prompts(3, "BUILD-THIS-EXACT-STRING")
    for p in prompts:
        assert "BUILD-THIS-EXACT-STRING" in p


def test_spawn_prompts_carry_topology_axis_guidance():
    prompts = spawn_prompts(3, "task")
    # Each prompt should mention some topology axis to push divergence.
    for p in prompts:
        assert "topology axis" in p.lower()


def test_spawn_prompts_embed_disagreement_when_present():
    d = _disagreement()
    prompts = spawn_prompts(2, "task", disagreement=d)
    # At least one prompt should reference the disagreement summary.
    assert any(d.summary in p for p in prompts)


def test_spawn_prompts_force_non_obvious_inserts_p_reframe():
    prompts = spawn_prompts(3, "task", force_non_obvious=2)
    assert "P_reframe" in prompts[2]
    assert "P_reframe" not in prompts[0]


def test_spawn_prompts_two_branches_split_disagreement():
    d = _disagreement()
    prompts = spawn_prompts(2, "task", disagreement=d)
    # Branch 0 should anchor on one side, branch 1 on the other (research vs self-eval).
    has_research = sum(1 for p in prompts if "research" in p.lower())
    has_selfeval = sum(1 for p in prompts if "self-eval" in p.lower())
    assert has_research >= 1
    assert has_selfeval >= 1


# ---------------------------------------------------------------------------
# validate_divergence


def test_validate_divergence_returns_a_report():
    branches = [
        Branch(id="b1", prompt="p", output="def x(): return 1"),
        Branch(id="b2", prompt="p", output="class Y:\n    pass"),
    ]
    report = validate_divergence(branches)
    assert isinstance(report, DivergenceReport)


def test_validate_divergence_reads_branch_outputs():
    # Identical outputs → collapsed.
    branches = [
        Branch(id="b1", prompt="p", output="def x(): return 1"),
        Branch(id="b2", prompt="p", output="def x(): return 1"),
    ]
    report = validate_divergence(branches)
    assert report.verdict == "collapsed"


def test_validate_divergence_threshold_passthrough():
    branches = [
        Branch(id="b1", prompt="p", output="def x(): return 1"),
        Branch(id="b2", prompt="p", output="def x():\n    return 1\n"),  # whitespace diff
    ]
    # Default thresholds treat these as collapsed (same topology). With strict thresholds
    # they become divergent (anything < 1.0 falls below).
    strict = validate_divergence(branches, collapsed_at=1.001, divergent_below=1.001)
    assert strict.verdict == "divergent"


# ---------------------------------------------------------------------------
# respawn_plan


def test_respawn_plan_divergent_proceeds():
    branches = [
        Branch(id="b1", prompt="p", output="def f(): pass"),
        Branch(
            id="b2",
            prompt="p",
            output="class C:\n    def __init__(self):\n        self.x = 1",
        ),
        Branch(
            id="b3",
            prompt="p",
            output="async def g():\n    await x()\n    for i in range(10):\n        yield i",
        ),
    ]
    report = validate_divergence(branches)
    plan = respawn_plan(report)
    if report.verdict == "divergent":
        assert plan.action == "proceed"
        assert plan.pair_indices is None


def test_respawn_plan_low_variance_targets_pair():
    branches = [
        Branch(id="b1", prompt="p", output="def add(a, b): return a + b"),
        Branch(id="b2", prompt="p", output="def sum(x, y): return x + y"),
        Branch(id="b3", prompt="p", output="class C:\n    def m(self): return None"),
    ]
    report = validate_divergence(branches)
    plan = respawn_plan(report)
    if report.verdict == "low-variance":
        assert plan.action == "respawn-pair"
        assert plan.pair_indices is not None


def test_respawn_plan_collapsed_aborts():
    branches = [
        Branch(id="b1", prompt="p", output="def x(): return 1"),
        Branch(id="b2", prompt="p", output="def x(): return 1"),
    ]
    report = validate_divergence(branches)
    plan = respawn_plan(report)
    assert plan.action == "abort"
    assert plan.pair_indices is None


def test_respawn_plan_is_immutable():
    plan = RespawnPlan(action="proceed", pair_indices=None, reason="x")
    with pytest.raises((AttributeError, TypeError)):
        plan.action = "abort"  # type: ignore[misc]
