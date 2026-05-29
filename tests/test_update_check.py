"""Tests for the SessionStart update-check hook.

The hook prints a one-line banner when a newer PQA release exists. It must:
never block (always exit 0), never make a network call when a fresh cache exists,
fail silent on any network/parse error, and stay stdlib-only. These tests drive
the pure logic with an injected fetcher + clock so no real network is touched.
"""

import importlib.util
import json
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOK_PATH = _REPO_ROOT / "hooks" / "update_check.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("update_check", _HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uc = _load_hook()


# ---------------------------------------------------------------------------
# Version parsing + comparison


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("v0.2.5", (0, 2, 5)), ("0.2.5", (0, 2, 5)), ("V1.0", (1, 0)), ("  v2.3.4 ", (2, 3, 4))],
)
def test_parse_version_handles_prefix_and_whitespace(raw, expected):
    assert uc.parse_version(raw) == expected


@pytest.mark.parametrize("raw", ["", "latest", "v1.x.0", "abc", "1.2.beta"])
def test_parse_version_returns_none_on_garbage(raw):
    assert uc.parse_version(raw) is None


def test_is_newer_true_when_latest_greater():
    assert uc.is_newer("0.2.5", "0.2.4") is True
    assert uc.is_newer("v0.3.0", "0.2.9") is True
    assert uc.is_newer("1.0.0", "0.9.9") is True


def test_is_newer_false_when_equal_or_older():
    assert uc.is_newer("0.2.4", "0.2.4") is False
    assert uc.is_newer("0.2.3", "0.2.4") is False


def test_is_newer_false_on_unparseable():
    assert uc.is_newer("garbage", "0.2.4") is False
    assert uc.is_newer("0.2.5", "garbage") is False


# ---------------------------------------------------------------------------
# Installed-version source


def test_read_installed_version_reads_file(tmp_path: Path):
    vf = tmp_path / "PQA_VERSION"
    vf.write_text("0.2.5\n")
    assert uc.read_installed_version(vf) == "0.2.5"


def test_read_installed_version_none_when_missing(tmp_path: Path):
    assert uc.read_installed_version(tmp_path / "nope") is None


# ---------------------------------------------------------------------------
# Banner


def test_format_banner_mentions_both_versions():
    banner = uc.format_banner("0.2.5", "0.2.4")
    assert "0.2.5" in banner
    assert "0.2.4" in banner


def test_compute_banner_emits_when_newer():
    assert uc.compute_banner("0.2.4", "0.2.5") is not None


def test_compute_banner_silent_when_up_to_date():
    assert uc.compute_banner("0.2.5", "0.2.5") is None
    assert uc.compute_banner("0.2.5", "0.2.4") is None  # installed ahead of latest


def test_compute_banner_silent_when_latest_unknown():
    # Offline / failed fetch yields no latest -> no banner, never an error.
    assert uc.compute_banner("0.2.4", None) is None
    assert uc.compute_banner(None, "0.2.5") is None


# ---------------------------------------------------------------------------
# Caching: network only when the cache is stale


def test_latest_version_uses_fresh_cache_without_network(tmp_path: Path):
    cache = tmp_path / "update_check.json"
    cache.write_text(json.dumps({"checked_at": 1000.0, "latest": "v9.9.9"}))

    def _must_not_fetch():
        raise AssertionError("network must not be hit when cache is fresh")

    # now is within the TTL window of checked_at
    result = uc.latest_version(cache, now=1000.0 + 60, fetch=_must_not_fetch)
    assert result == "v9.9.9"


def test_latest_version_fetches_when_cache_stale_and_rewrites(tmp_path: Path):
    cache = tmp_path / "update_check.json"
    stale_ts = 1000.0
    cache.write_text(json.dumps({"checked_at": stale_ts, "latest": "v0.0.1"}))
    now = stale_ts + uc.CACHE_TTL_SECONDS + 1

    result = uc.latest_version(cache, now=now, fetch=lambda: "v0.2.5")
    assert result == "v0.2.5"
    rewritten = json.loads(cache.read_text())
    assert rewritten["latest"] == "v0.2.5"
    assert rewritten["checked_at"] == now


def test_latest_version_fetches_when_no_cache(tmp_path: Path):
    cache = tmp_path / "update_check.json"  # does not exist
    result = uc.latest_version(cache, now=2000.0, fetch=lambda: "v0.2.5")
    assert result == "v0.2.5"
    assert cache.exists()


def test_latest_version_returns_none_when_fetch_fails_and_no_cache(tmp_path: Path):
    cache = tmp_path / "update_check.json"
    assert uc.latest_version(cache, now=2000.0, fetch=lambda: None) is None


# ---------------------------------------------------------------------------
# Version drift guard (the audit flagged manifest/pyproject drift)


def test_all_version_sources_agree():
    """hooks/PQA_VERSION, pyproject, and both plugin manifests must match — this is
    the file the hook reports as 'installed', so drift would mislead users."""
    pqa_version = (_REPO_ROOT / "hooks" / "PQA_VERSION").read_text().strip()
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())["project"]["version"]
    plugin = json.loads((_REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    market = json.loads((_REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    market_version = market["plugins"][0]["version"]
    assert pqa_version == pyproject == plugin == market_version, (
        f"version drift: PQA_VERSION={pqa_version} pyproject={pyproject} "
        f"plugin={plugin} marketplace={market_version}"
    )
