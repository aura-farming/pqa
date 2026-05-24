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
