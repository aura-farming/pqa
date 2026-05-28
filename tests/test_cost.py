"""Tests for the cost-governor: per-run budget cap, live spend tracking, hard abort.

The contract: a run that crosses its dollar cap must report `abort`, regardless of how the
spend was distributed across branches. Tokens are tracked truthfully; cost is derived from
a model price table so a Sonnet branch and an Opus branch are not weighted the same.
"""

import threading

import pytest

from pqa.cost import MODEL_PRICING, Budget, CostGovernor, Spend, cost_for


def test_cost_for_opus_pricing():
    # Opus 4.7: $15/Mtok input, $75/Mtok output.
    assert cost_for("claude-opus-4-7", 1_000_000, 0) == pytest.approx(15.0)
    assert cost_for("claude-opus-4-7", 0, 1_000_000) == pytest.approx(75.0)


def test_cost_for_sonnet_is_cheaper_than_opus():
    sonnet = cost_for("claude-sonnet-4-6", 100_000, 50_000)
    opus = cost_for("claude-opus-4-7", 100_000, 50_000)
    assert sonnet < opus


def test_cost_for_unknown_model_raises():
    with pytest.raises(KeyError):
        cost_for("not-a-model", 1, 1)


def test_governor_records_spend_per_branch():
    g = CostGovernor(Budget(max_usd=10.0))
    g.record("b1", "claude-sonnet-4-6", 1_000, 500)
    g.record("b2", "claude-opus-4-7", 1_000, 500)
    per = g.per_branch()
    assert set(per.keys()) == {"b1", "b2"}
    assert per["b1"].input_tokens == 1_000
    assert per["b2"].output_tokens == 500


def test_governor_accumulates_repeated_records():
    g = CostGovernor(Budget(max_usd=10.0))
    g.record("b1", "claude-sonnet-4-6", 1_000, 500)
    g.record("b1", "claude-sonnet-4-6", 1_000, 500)
    assert g.per_branch()["b1"].input_tokens == 2_000
    assert g.per_branch()["b1"].output_tokens == 1_000


def test_governor_total_sums_across_branches():
    g = CostGovernor(Budget(max_usd=10.0))
    g.record("b1", "claude-sonnet-4-6", 1_000, 500)
    g.record("b2", "claude-sonnet-4-6", 2_000, 250)
    total = g.total()
    assert total.input_tokens == 3_000
    assert total.output_tokens == 750


def test_governor_status_ok_warn_abort_progression():
    g = CostGovernor(Budget(max_usd=1.0, warn_at=0.5))
    assert g.status() == "ok"
    # Sonnet input is $3/Mtok, so 100k input = $0.30 → still ok against $1 cap.
    g.record("b", "claude-sonnet-4-6", 100_000, 0)
    assert g.status() == "ok"
    # Reach $0.60 → above 50% warn line, below cap.
    g.record("b", "claude-sonnet-4-6", 100_000, 0)
    assert g.status() == "warn"
    # Push over the cap.
    g.record("b", "claude-sonnet-4-6", 300_000, 0)
    assert g.status() == "abort"


def test_should_abort_only_true_past_cap():
    g = CostGovernor(Budget(max_usd=0.10))
    assert not g.should_abort()
    g.record("b", "claude-opus-4-7", 1_000_000, 0)  # $15 → way over
    assert g.should_abort()


def test_remaining_usd_never_negative():
    g = CostGovernor(Budget(max_usd=0.10))
    g.record("b", "claude-opus-4-7", 1_000_000, 0)  # blow past
    assert g.remaining_usd() == 0.0


def test_remaining_usd_decreases_with_spend():
    g = CostGovernor(Budget(max_usd=10.0))
    before = g.remaining_usd()
    g.record("b", "claude-sonnet-4-6", 100_000, 0)  # $0.30
    after = g.remaining_usd()
    assert before - after == pytest.approx(0.30)


def test_record_zero_tokens_is_a_noop():
    g = CostGovernor(Budget(max_usd=1.0))
    g.record("b", "claude-opus-4-7", 0, 0)
    assert g.total().cost_usd == 0.0
    assert g.status() == "ok"


def test_negative_tokens_rejected():
    g = CostGovernor(Budget(max_usd=1.0))
    with pytest.raises(ValueError):
        g.record("b", "claude-opus-4-7", -1, 0)
    with pytest.raises(ValueError):
        g.record("b", "claude-opus-4-7", 0, -1)


def test_budget_must_be_positive():
    with pytest.raises(ValueError):
        Budget(max_usd=0)
    with pytest.raises(ValueError):
        Budget(max_usd=-5)


def test_warn_at_must_be_between_0_and_1():
    with pytest.raises(ValueError):
        Budget(max_usd=1.0, warn_at=0)
    with pytest.raises(ValueError):
        Budget(max_usd=1.0, warn_at=1.0)


def test_concurrent_records_are_thread_safe():
    g = CostGovernor(Budget(max_usd=10_000.0))

    def worker(branch: str) -> None:
        for _ in range(100):
            g.record(branch, "claude-sonnet-4-6", 100, 100)

    threads = [threading.Thread(target=worker, args=(f"b{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = g.total()
    assert total.input_tokens == 8 * 100 * 100
    assert total.output_tokens == 8 * 100 * 100


def test_report_includes_total_status_remaining_and_branches():
    g = CostGovernor(Budget(max_usd=1.0))
    g.record("baseline", "claude-sonnet-4-6", 1_000, 500)
    g.record("pqa-b1", "claude-opus-4-7", 1_000, 500)
    report = g.report()
    assert "baseline" in report
    assert "pqa-b1" in report
    assert "status" in report.lower()
    assert "remaining" in report.lower()


def test_spend_default_is_zero():
    s = Spend()
    assert s.input_tokens == 0
    assert s.output_tokens == 0
    assert s.cost_usd == 0.0


def test_known_models_priced():
    assert {"claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"} <= MODEL_PRICING.keys()


# ---------------------------------------------------------------------------
# TOCTOU consistency — every observable comes from a single lock acquisition
# (audit findings #1 and #2)


def test_report_status_matches_displayed_spend():
    """report()'s status line must agree with the spent/remaining values displayed in
    the same report. Previously these were separate lock acquisitions, so the report
    could show status=ok while the snapshot already reflected abort."""
    g = CostGovernor(Budget(max_usd=1.0))
    g.record("b", "claude-sonnet-4-6", 400_000, 0)  # $1.20 → past cap
    report = g.report()
    assert "status: abort" in report
    # And the spent line shows a number actually past the cap.
    assert "$1.2000 of $1.00" in report or "$1.20" in report


def test_should_abort_is_single_lock_acquisition():
    """Smoke: should_abort should not deadlock or split-read under contention."""
    g = CostGovernor(Budget(max_usd=10_000.0))
    aborts: list[bool] = []

    def hammer():
        for _ in range(500):
            g.record("b", "claude-sonnet-4-6", 10, 10)
            aborts.append(g.should_abort())

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # No deadlock; final state is stable.
    assert g.total().input_tokens == 4 * 500 * 10
    assert not g.should_abort()  # well under budget


# ---------------------------------------------------------------------------
# Pre-flight projection — would_abort() gates a not-yet-recorded dispatch
# against the budget cap (issue #32).


def test_would_abort_false_when_projection_under_cap():
    g = CostGovernor(Budget(max_usd=10.0))
    # Opus: $15/Mtok in, $75/Mtok out. Project 10k in, 5k out = $0.525.
    assert g.would_abort("claude-opus-4-7", 10_000, 5_000) is False


def test_would_abort_true_when_projection_past_cap():
    g = CostGovernor(Budget(max_usd=0.10))
    # 1M Opus input tokens projects to $15 — way past $0.10 cap.
    assert g.would_abort("claude-opus-4-7", 1_000_000, 0) is True


def test_would_abort_accounts_for_already_recorded_spend():
    g = CostGovernor(Budget(max_usd=1.0))
    g.record("b0", "claude-sonnet-4-6", 200_000, 0)  # $0.60 recorded
    # Project $0.15 more (50k Sonnet input) → $0.75 total, still under $1.00.
    assert g.would_abort("claude-sonnet-4-6", 50_000, 0) is False
    # Now project $0.60 more (200k Sonnet input) → $1.20 total, past cap.
    assert g.would_abort("claude-sonnet-4-6", 200_000, 0) is True


def test_would_abort_at_exact_cap_boundary_is_true():
    # status_from uses >= for abort, so projecting exactly to the cap aborts.
    g = CostGovernor(Budget(max_usd=1.0))
    # $1.00 = 1/3 Mtok Sonnet input ($3/Mtok). Use exact arithmetic.
    tokens_for_one_dollar = 1_000_000 // 3 + 1  # rounded up — strictly past $1.00
    assert g.would_abort("claude-sonnet-4-6", tokens_for_one_dollar, 0) is True


def test_would_abort_opus_costs_more_than_sonnet():
    g = CostGovernor(Budget(max_usd=1.0))
    # Same token counts, different models — Opus must be more likely to abort.
    sonnet_aborts = g.would_abort("claude-sonnet-4-6", 100_000, 0)  # $0.30
    opus_aborts = g.would_abort("claude-opus-4-7", 100_000, 0)  # $1.50
    assert sonnet_aborts is False
    assert opus_aborts is True


def test_would_abort_unknown_model_raises():
    g = CostGovernor(Budget(max_usd=1.0))
    with pytest.raises(KeyError):
        g.would_abort("not-a-model", 1_000, 1_000)


def test_would_abort_negative_projection_raises():
    g = CostGovernor(Budget(max_usd=1.0))
    with pytest.raises(ValueError):
        g.would_abort("claude-opus-4-7", -1, 0)
    with pytest.raises(ValueError):
        g.would_abort("claude-opus-4-7", 0, -1)


def test_would_abort_zero_projection_reflects_current_state_only():
    g = CostGovernor(Budget(max_usd=1.0))
    # Zero projection on empty governor: clearly fine.
    assert g.would_abort("claude-opus-4-7", 0, 0) is False
    # Push past cap, then zero projection still reports abort.
    g.record("b", "claude-opus-4-7", 100_000, 0)  # $1.50, over cap
    assert g.would_abort("claude-opus-4-7", 0, 0) is True


def test_would_abort_is_non_mutating():
    g = CostGovernor(Budget(max_usd=10.0))
    g.record("b0", "claude-sonnet-4-6", 1_000, 500)
    snapshot_total_before = g.total()
    snapshot_per_branch_before = g.per_branch()
    # Several projections, including one that would abort.
    g.would_abort("claude-opus-4-7", 10_000, 5_000)
    g.would_abort("claude-opus-4-7", 1_000_000, 1_000_000)
    g.would_abort("claude-sonnet-4-6", 0, 0)
    # State must be unchanged — projection is read-only.
    assert g.total() == snapshot_total_before
    assert g.per_branch() == snapshot_per_branch_before


def test_would_abort_thread_safe_under_concurrent_record():
    """would_abort under contention with record() must not deadlock or split-read."""
    g = CostGovernor(Budget(max_usd=10_000.0))

    def recorder() -> None:
        for _ in range(500):
            g.record("b", "claude-sonnet-4-6", 10, 10)

    def projector() -> None:
        for _ in range(500):
            # Doesn't matter whether True or False — just that it returns cleanly.
            g.would_abort("claude-sonnet-4-6", 100, 100)

    threads = [
        threading.Thread(target=recorder),
        threading.Thread(target=recorder),
        threading.Thread(target=projector),
        threading.Thread(target=projector),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Final state stable; no deadlock.
    assert g.total().input_tokens == 2 * 500 * 10
    assert not g.should_abort()
