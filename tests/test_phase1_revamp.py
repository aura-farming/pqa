"""Tests for the Phase-1 revamp: corrected economics, alias wiring, token budgets,
respawn-pair, spiral guard, and filesystem-safe report ids.

These pin the behaviours the roadmap (docs/WORLD-CLASS-ROADMAP.md §3) calls P0:
a default run must be able to complete, model identity must flow one way from
config/branch to pricing, and silent path escapes must be impossible.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pqa.collapse import CollapseOutcome
from pqa.config import load_or_defaults
from pqa.cost import (
    MODEL_ALIASES,
    MODEL_PRICING,
    PRICING_AS_OF,
    Budget,
    CostGovernor,
    cost_for,
    resolve_model,
)
from pqa.frame import Frame
from pqa.memory import connect
from pqa.orchestrator import RunReport, VerifyResult, run
from pqa.report import write_report
from pqa.superposition import Branch

# ---------------------------------------------------------------------------
# Pricing + aliases


def test_pricing_table_matches_published_rates():
    """Pin the table to the vendor-published standard-tier rates as of PRICING_AS_OF.
    If this fails, someone edited prices without re-verifying against the docs —
    update BOTH the table and PRICING_AS_OF together."""
    assert MODEL_PRICING == {
        "claude-fable-5": (10.0, 50.0),
        "claude-opus-4-8": (5.0, 25.0),
        "claude-opus-4-7": (5.0, 25.0),
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-haiku-4-5": (1.0, 5.0),
    }
    year, month, day = PRICING_AS_OF.split("-")
    assert len(year) == 4 and len(month) == 2 and len(day) == 2


def test_every_alias_resolves_to_a_priced_model():
    for alias in MODEL_ALIASES:
        assert resolve_model(alias) in MODEL_PRICING


def test_resolve_model_passes_concrete_ids_through():
    assert resolve_model("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_resolve_model_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        resolve_model("gpt-9000")


def test_cost_for_accepts_aliases():
    assert cost_for("opus", 1_000_000, 0) == pytest.approx(5.0)
    assert cost_for("fable", 1_000_000, 0) == pytest.approx(10.0)


def test_governor_records_alias_spend():
    g = CostGovernor(Budget(max_usd=10.0))
    g.record("b0", "opus", 100_000, 10_000)  # was a KeyError before the alias wiring
    assert g.total().cost_usd == pytest.approx(0.5 + 0.25)


# ---------------------------------------------------------------------------
# Token-primary budget


def test_budget_rejects_non_positive_max_tokens():
    with pytest.raises(ValueError):
        Budget(max_usd=1.0, max_tokens=0)


def test_token_cap_aborts_independent_of_usd():
    g = CostGovernor(Budget(max_usd=1_000.0, max_tokens=10_000))
    g.record("b0", "claude-haiku-4-5", 9_000, 1_000)  # pennies in USD, at token cap
    assert g.status() == "abort"
    assert g.should_abort() is True


def test_token_cap_warns_at_threshold():
    g = CostGovernor(Budget(max_usd=1_000.0, warn_at=0.8, max_tokens=10_000))
    g.record("b0", "claude-haiku-4-5", 8_000, 0)
    assert g.status() == "warn"


def test_would_abort_projects_tokens():
    g = CostGovernor(Budget(max_usd=1_000.0, max_tokens=10_000))
    g.record("b0", "claude-haiku-4-5", 5_000, 0)
    assert g.would_abort("claude-haiku-4-5", 5_000, 0) is True
    assert g.would_abort("claude-haiku-4-5", 1_000, 0) is False


def test_remaining_tokens():
    g = CostGovernor(Budget(max_usd=1.0, max_tokens=10_000))
    assert g.remaining_tokens() == 10_000
    g.record("b0", "claude-haiku-4-5", 1_000, 500)
    assert g.remaining_tokens() == 8_500
    assert CostGovernor(Budget(max_usd=1.0)).remaining_tokens() is None


def test_report_includes_token_budget_line():
    g = CostGovernor(Budget(max_usd=1.0, max_tokens=10_000))
    g.record("b0", "claude-haiku-4-5", 1_000, 500)
    assert "token budget: 1,500 of 10,000" in g.report()


# ---------------------------------------------------------------------------
# Config wiring


def test_config_resolved_model_maps_alias_to_dispatch_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("PQA_MODEL", "opus")
    cfg = load_or_defaults(tmp_path / "absent.toml")
    assert cfg.resolved_model() == "claude-opus-4-8"


def test_config_rejects_token_budget_below_floor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("PQA_RUN_BUDGET_TOKENS", "5000")
    with pytest.raises(ValueError):
        load_or_defaults(tmp_path / "absent.toml")


def test_config_rejects_out_of_range_spiral_depth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("PQA_MAX_SPIRAL_DEPTH", "9")
    with pytest.raises(ValueError):
        load_or_defaults(tmp_path / "absent.toml")


def test_config_rejects_unknown_branches_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("PQA_BRANCHES_MODE", "teleport")
    with pytest.raises(ValueError):
        load_or_defaults(tmp_path / "absent.toml")


def test_config_accepts_fable_alias(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PQA_MODEL", "fable")
    cfg = load_or_defaults(tmp_path / "absent.toml")
    assert cfg.resolved_model() == "claude-fable-5"


# ---------------------------------------------------------------------------
# Orchestrator: respawn-pair honours the divergence gate

_B0 = "def f(a, b):\n    total = a + b\n    return total\n"
# AST-similar to _B0 (one extra statement): similarity ~0.865 -> 'low-variance',
# which is exactly the respawn-pair band (0.7 <= s < 0.95).
_B1_TOO_SIMILAR = "def f(a, b):\n    total = a + b\n    print(total)\n    return total\n"
# Structurally different (class + state): similarity ~0.185 vs _B0 -> 'divergent'.
_B1_RESPAWNED = (
    "class Adder:\n"
    "    def __init__(self):\n"
    "        self.history = []\n"
    "    def add(self, *args):\n"
    "        r = sum(args)\n"
    "        self.history.append(r)\n"
    "        return r\n"
)


def _frame(kind: str, content: str) -> Frame:
    return Frame(type=kind, content=content, source="test")


def _respawning_generator() -> tuple[Callable[[Branch], tuple[Branch, int, int]], list[str]]:
    """First pass: b1 converges with b0. Respawn pass (STRONGER reframe in prompt):
    b1 takes a genuinely different topology."""
    calls: list[str] = []

    def generate(branch: Branch) -> tuple[Branch, int, int]:
        calls.append(branch.id)
        if branch.id == "b1" and "STRONGER" in branch.prompt:
            out = _B1_RESPAWNED
        elif branch.id == "b1":
            out = _B1_TOO_SIMILAR
        else:
            out = _B0
        return (
            Branch(
                id=branch.id,
                prompt=branch.prompt,
                output=out,
                incremental=branch.incremental,
                model=branch.model,
            ),
            1_000,
            500,
        )

    return generate, calls


def test_respawn_pair_regenerates_similar_branch(tmp_path: Path):
    conn = connect(tmp_path / "m.db")
    generator, calls = _respawning_generator()
    report = run(
        task="rate-limiter",
        session_id="respawn-test",
        base_prompt="solve it",
        research=_frame("research", "docs say use a token bucket"),
        selfeval=_frame("selfeval", "the queue is bursty so leaky-bucket fits here"),
        generator=generator,
        adversary=lambda _branches: ([], 100, 50),
        verifier=lambda _b: VerifyResult(has_tests=True, verified=True, coverage=90.0),
        budget=Budget(max_usd=10.0),
        conn=conn,
        n_branches=2,
    )
    conn.close()
    assert report.aborted is False
    assert calls.count("b1") == 2  # initial generation + one respawn
    respawned = next(b for b in report.branches if b.id == "b1")
    assert "Adder" in respawned.output
    assert report.divergence is not None
    assert report.divergence.verdict == "divergent"


def test_respawn_records_extra_spend(tmp_path: Path):
    conn = connect(tmp_path / "m.db")
    generator, calls = _respawning_generator()
    report = run(
        task="t",
        session_id="respawn-spend",
        base_prompt="solve it",
        research=_frame("research", "docs say use a token bucket"),
        selfeval=_frame("selfeval", "the queue is bursty so leaky-bucket fits here"),
        generator=generator,
        adversary=lambda _branches: ([], 100, 50),
        verifier=lambda _b: VerifyResult(has_tests=True, verified=True, coverage=90.0),
        budget=Budget(max_usd=10.0),
        conn=conn,
        n_branches=2,
    )
    conn.close()
    # 3 generator calls (b0, b1, b1-respawn) at 1,500 tokens each + adversary 150.
    assert len(calls) == 3
    assert "in=3,100" in report.cost_report


def test_spiral_depth_guard_aborts(tmp_path: Path):
    conn = connect(tmp_path / "m.db")
    generator, _calls = _respawning_generator()
    report = run(
        task="t",
        session_id="spiral-test",
        base_prompt="solve it",
        research=_frame("research", "docs say use a token bucket"),
        selfeval=_frame("selfeval", "the queue is bursty so leaky-bucket fits here"),
        generator=generator,
        adversary=lambda _branches: ([], 1, 1),
        verifier=lambda _b: VerifyResult(has_tests=False, verified=False, coverage=None),
        budget=Budget(max_usd=10.0),
        conn=conn,
        n_branches=2,
        spiral_depth=2,
        max_spiral_depth=1,
    )
    conn.close()
    assert report.aborted is True
    assert report.abort_reason is not None
    assert "spiral depth" in report.abort_reason


# ---------------------------------------------------------------------------
# Report: filesystem-safe session ids


def _minimal_report(session_id: str) -> RunReport:
    return RunReport(
        task="t",
        session_id=session_id,
        survivor=None,
        survivor_result=None,
        collapse=CollapseOutcome(None, "r", False, "aborted"),
        divergence=None,
        cost_report="",
        baseline_comparison=None,
        branches=(),
        branch_results=(),
        aborted=True,
        abort_reason="x",
        started_at=0,
        finished_at=0,
    )


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", ".hidden", "", "a" * 200])
def test_write_report_rejects_unsafe_session_ids(bad: str, tmp_path: Path):
    with pytest.raises(ValueError):
        write_report(_minimal_report(bad), root=tmp_path)


def test_write_report_accepts_safe_session_id(tmp_path: Path):
    artefact = write_report(_minimal_report("run-2026.06_10-a1"), root=tmp_path)
    assert artefact.json_path.exists()
    assert artefact.markdown_path.exists()
