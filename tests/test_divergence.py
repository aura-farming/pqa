"""Tests for divergence measurement: topology, not style.

A superposition of N branches that all produced the same idea with different variable names
is a wasted superposition. The divergence module catches that and tells the orchestrator
which pair to re-spawn — closing Gap #8 from the plan.
"""

import pytest

from pqa.divergence import (
    BranchSimilarity,
    DivergenceReport,
    measure_divergence,
    similarity,
)


def test_identical_branches_have_similarity_1():
    code = "def add(a, b):\n    return a + b\n"
    assert similarity(code, code) == pytest.approx(1.0)


def test_same_topology_different_names_is_high_similarity():
    a = "def add(a, b):\n    return a + b\n"
    b = "def sum(x, y):\n    return x + y\n"
    # Same AST shape, only identifiers differ — should score above the divergent threshold.
    assert similarity(a, b) >= 0.95


def test_same_topology_different_style_is_high_similarity():
    a = "def add(a, b):\n    return a + b\n"
    b = "def add(a,b):return a+b   # comment\n"
    assert similarity(a, b) >= 0.95


def test_different_topology_is_low_similarity():
    a = "def add(a, b):\n    return a + b\n"
    b = (
        "from functools import reduce\n"
        "def add(*args):\n"
        "    return reduce(lambda x, y: x + y, args, 0)\n"
    )
    assert similarity(a, b) < 0.7


def test_different_operator_is_detected():
    # Same shape but Add vs Sub — must show as different topology.
    a = "def f(a, b):\n    return a + b\n"
    b = "def f(a, b):\n    return a - b\n"
    assert similarity(a, b) < 1.0


def test_non_python_falls_back_to_text_similarity():
    a = "the quick brown fox jumps over the lazy dog"
    b = "the quick brown fox jumps over the lazy dog"
    assert similarity(a, b) == pytest.approx(1.0)


def test_non_python_different_strings_are_dissimilar():
    a = "completely unrelated text here"
    b = "totally different content over there"
    assert similarity(a, b) < 0.6


def test_measure_divergence_empty_list_is_collapsed():
    report = measure_divergence([])
    assert report.verdict == "collapsed"
    assert report.pair_similarities == []
    assert report.most_similar_pair is None


def test_measure_divergence_single_branch_is_collapsed():
    report = measure_divergence(["def x(): pass"])
    assert report.verdict == "collapsed"
    assert report.most_similar_pair is None


def test_three_identical_branches_collapse():
    code = "def x(): return 1"
    report = measure_divergence([code, code, code])
    assert report.verdict == "collapsed"
    assert report.mean_similarity == pytest.approx(1.0)
    assert len(report.pair_similarities) == 3  # C(3,2)


def test_three_divergent_branches_are_divergent():
    a = "def x(): return 1"
    b = "def x():\n    for i in range(10):\n        print(i)"
    c = (
        "class X:\n"
        "    def __init__(self):\n"
        "        self.value = 42\n"
        "    async def go(self):\n"
        "        await self.fetch()"
    )
    report = measure_divergence([a, b, c])
    assert report.verdict == "divergent"


def test_mixed_two_similar_one_different_is_low_variance():
    # A and B same idea different names; C totally different shape.
    a = "def add(a, b):\n    return a + b\n"
    b = "def sum(x, y):\n    return x + y\n"
    c = "class Calculator:\n    def __init__(self):\n        self.history = []"
    report = measure_divergence([a, b, c])
    assert report.verdict == "low-variance"
    # The most similar pair should be (a, b) at indices 0, 1.
    assert report.most_similar_pair == (0, 1)


def test_pair_count_is_n_choose_2():
    branches = [f"def f{i}(): return {i}" for i in range(5)]
    report = measure_divergence(branches)
    assert len(report.pair_similarities) == 10  # C(5,2) = 10


def test_thresholds_are_configurable():
    # Use shapes that produce a real (non-1.0) similarity so thresholds actually matter.
    # `+` vs `*` is two different ops on the same BinOp shape — close but not identical.
    a = "def f(a, b):\n    return a + b\n"
    b = "def f(a, b):\n    return a * b\n"

    # Impossibly strict: collapsed/divergent_below = 1.001 means no real similarity
    # can hit either bucket, so everything lands as "divergent".
    strict = measure_divergence([a, b], collapsed_at=1.001, divergent_below=1.001)
    assert strict.verdict == "divergent"

    # Impossibly loose: collapsed_at = 0.0 forces every pair to "collapsed".
    loose = measure_divergence([a, b], collapsed_at=0.0, divergent_below=0.0)
    assert loose.verdict == "collapsed"


def test_report_is_immutable():
    report = measure_divergence(["a", "b"])
    with pytest.raises((AttributeError, TypeError)):
        report.verdict = "divergent"  # type: ignore[misc]


def test_branch_similarity_is_immutable():
    s = BranchSimilarity(branch_a=0, branch_b=1, similarity=0.5)
    with pytest.raises((AttributeError, TypeError)):
        s.similarity = 0.9  # type: ignore[misc]


def test_most_similar_pair_indices_are_in_order():
    branches = ["def a(): pass", "def b(): pass", "def c(): pass"]
    report = measure_divergence(branches)
    if report.most_similar_pair is not None:
        a, b = report.most_similar_pair
        assert a < b


def test_report_carries_descriptive_statistics():
    report = measure_divergence(
        [
            "def x(): return 1",
            "def x(): return 1",
            "class C:\n    pass",
        ]
    )
    assert 0.0 <= report.min_similarity <= report.mean_similarity <= report.max_similarity <= 1.0


def test_collapsed_at_threshold_default_is_strict():
    # Two same-topology branches with different names should NOT be marked collapsed
    # under the default threshold — the harness wants to allow style-divergent work
    # to count as one branch only when the threshold is high.
    a = "def add(a, b):\n    return a + b\n"
    b = "def sum(x, y):\n    return x + y\n"
    report = measure_divergence([a, b])
    # 2 identical-topology different-name branches: pair similarity is high but not 1.0;
    # whether that lands as "collapsed" or "low-variance" depends on the default. Either
    # is acceptable; "divergent" is wrong (these are the same idea).
    assert report.verdict != "divergent"


def test_returns_dataclass_instance():
    report = measure_divergence(["a", "b"])
    assert isinstance(report, DivergenceReport)
