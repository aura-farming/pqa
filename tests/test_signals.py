"""Tests for conviction signal parsing."""
from pqa.signals import parse_conviction


def test_parses_high_conviction():
    sig = parse_conviction("conviction: high, basis: reframing it as a stream removes the queue")
    assert sig is not None
    assert sig.level == "high"
    assert "stream" in sig.basis
    assert sig.protects_from_pruning is True


def test_medium_conviction_does_not_protect():
    sig = parse_conviction("conviction: medium, basis: probably fine")
    assert sig.level == "medium"
    assert sig.protects_from_pruning is False


def test_no_signal_returns_none():
    assert parse_conviction("just a normal branch with no flag") is None


def test_case_insensitive():
    assert parse_conviction("CONVICTION: HIGH, BASIS: x").level == "high"
