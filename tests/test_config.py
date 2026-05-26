"""Locked behaviour contract for pqa.config.load_config.

These tests describe the minimum surface every PQA superposition branch must
satisfy. They were committed to the branches' base ref before the orchestrator
spawned generators — branches that author or modify these tests are flagged
as critical anomalies and excluded from collapse.

This is the TIGHTENED contract written after the first PQA round produced
no survivor on this task: three valid topologies all silently corrupted data
on wrong-typed values, unknown keys, and ambient env vars. The precipitate
named the cure — pin the axes where data integrity hinges, leave the rest open.

Behaviour pinned (the contract — branches CANNOT differ on these):
    1. `from pqa.config import load_config` is the canonical entry point.
    2. load_config(path) returns an immutable typed object exposing the five
       PQA settings (branches: int, verify_tests: bool, model: str,
       run_budget_usd: float, memory_db: str). Mutating an attribute raises.
    3. The loader accepts both str and pathlib.Path.
    4. A malformed TOML raises an exception that chains tomllib.TOMLDecodeError.
    5. A wrong-typed TOML value (e.g. branches = "seven", verify_tests = "true"
       as a string) raises — silent default substitution is forbidden because
       that is the data-corruption class the first round died on.
    6. A missing file raises FileNotFoundError (or wraps it via __cause__).
       Defaulting silently when the user named a path is data loss.
    7. An unknown key in the [pqa] table raises — silent ignore is the same
       data-corruption class as wrong-typed values (user typo → silent miss).
    8. Precedence is env > TOML > built-in defaults. PQA_* env vars override
       TOML; missing TOML keys fall through to defaults from config/settings.py.
    9. A malformed PQA_* env var (e.g. PQA_BRANCHES='three') raises a clear
       error — not a bare unchained ValueError at consumer attribute access.
   10. A partial TOML (some [pqa] keys present, others missing) uses defaults
       from config/settings.py for the missing keys — partial != error.

Behaviour deliberately NOT pinned (branches still differ here — the adversary
attacks the differences):
    - The exact internal module path under pqa/ — only the public symbol is locked.
    - The error type hierarchy (ConfigError class vs builtin TypeError/ValueError
      with chained __cause__) — branches choose error shape.
    - Eager vs lazy resolution under the hood (as long as observable behaviour
      matches the pins above).
    - Whether the loader is a class, function, or other callable shape.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from pqa.config import load_config


def _write_toml(path: Path, **overrides: object) -> Path:
    """Write a minimal pqa-config.toml with [pqa] section under the given path."""
    base: dict[str, object] = {
        "branches": 3,
        "verify_tests": False,
        "model": "opus",
        "run_budget_usd": 15.0,
        "memory_db": ".claude/hooks/memory/pqa_memory.db",
    }
    base.update(overrides)
    lines = ["[pqa]"]
    for key, value in base.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_load_config_returns_typed_object(tmp_path: Path) -> None:
    cfg = load_config(_write_toml(tmp_path / "pqa-config.toml"))
    assert isinstance(cfg.branches, int)
    assert isinstance(cfg.verify_tests, bool)
    assert isinstance(cfg.model, str)
    assert isinstance(cfg.run_budget_usd, float)
    assert isinstance(cfg.memory_db, str)


def test_load_config_reads_toml_values(tmp_path: Path) -> None:
    toml = _write_toml(
        tmp_path / "pqa-config.toml",
        branches=7,
        model="haiku",
        run_budget_usd=42.5,
        verify_tests=True,
    )
    cfg = load_config(toml)
    assert cfg.branches == 7
    assert cfg.model == "haiku"
    assert cfg.run_budget_usd == pytest.approx(42.5)
    assert cfg.verify_tests is True


def test_load_config_rejects_malformed_toml(tmp_path: Path) -> None:
    toml = tmp_path / "pqa-config.toml"
    toml.write_text("not = = valid [[[ toml")
    with pytest.raises(Exception) as exc_info:
        load_config(toml)
    chain: list[BaseException] = []
    current: BaseException | None = exc_info.value
    while current is not None:
        chain.append(current)
        current = current.__cause__ or current.__context__
    assert any(isinstance(exc, tomllib.TOMLDecodeError) for exc in chain), (
        "malformed-TOML must chain tomllib.TOMLDecodeError; raised "
        f"{type(exc_info.value).__name__} without it"
    )


def test_load_config_returns_immutable_object(tmp_path: Path) -> None:
    cfg = load_config(_write_toml(tmp_path / "pqa-config.toml"))
    with pytest.raises((AttributeError, TypeError)):
        cfg.branches = 999  # type: ignore[misc]


def test_load_config_accepts_str_or_path(tmp_path: Path) -> None:
    toml = _write_toml(tmp_path / "pqa-config.toml", branches=5)
    from_path = load_config(toml)
    from_str = load_config(str(toml))
    assert from_path.branches == from_str.branches == 5


# ---------------------------------------------------------------------------
# Tightened contract (spiral round) — pins the axes the first round died on.


def _write_raw_toml(path: Path, body: str) -> Path:
    """Write an arbitrary TOML body (used when overriding types or schema)."""
    path.write_text(body)
    return path


def test_load_config_rejects_wrong_typed_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """branches='seven' (string) must raise — silent default is data corruption."""
    monkeypatch.delenv("PQA_BRANCHES", raising=False)
    toml = _write_raw_toml(
        tmp_path / "pqa-config.toml", '[pqa]\nbranches = "seven"\nmodel = "opus"\n'
    )
    # B017 disabled: the locked contract intentionally leaves error-type unpinned —
    # branches may raise TypeError, ValueError, a custom ConfigError, or anything else;
    # only the fact that load_config raises is locked.
    with pytest.raises(Exception):  # noqa: B017
        load_config(toml)


def test_load_config_rejects_wrong_typed_verify_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """verify_tests = "true" (string, not bool) must raise — user typo must surface."""
    monkeypatch.delenv("PQA_VERIFY_TESTS", raising=False)
    toml = _write_raw_toml(
        tmp_path / "pqa-config.toml", '[pqa]\nverify_tests = "true"\nmodel = "opus"\n'
    )
    # B017 disabled: the locked contract intentionally leaves error-type unpinned —
    # branches may raise TypeError, ValueError, a custom ConfigError, or anything else;
    # only the fact that load_config raises is locked.
    with pytest.raises(Exception):  # noqa: B017
        load_config(toml)


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    """Missing file → FileNotFoundError (raw or chained). Silent default is data loss."""
    missing = tmp_path / "does-not-exist.toml"
    with pytest.raises(Exception) as exc_info:
        load_config(missing)
    chain: list[BaseException] = []
    current: BaseException | None = exc_info.value
    while current is not None:
        chain.append(current)
        current = current.__cause__ or current.__context__
    assert any(isinstance(exc, FileNotFoundError) for exc in chain), (
        "missing-file must chain FileNotFoundError; raised "
        f"{type(exc_info.value).__name__} without it"
    )


def test_load_config_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """env > TOML. PQA_BRANCHES=42 with TOML branches=7 → cfg.branches == 42."""
    monkeypatch.setenv("PQA_BRANCHES", "42")
    monkeypatch.setenv("PQA_MODEL", "haiku-from-env")
    toml = _write_toml(tmp_path / "pqa-config.toml", branches=7, model="opus-from-toml")
    cfg = load_config(toml)
    assert cfg.branches == 42
    assert cfg.model == "haiku-from-env"


def test_load_config_rejects_unknown_pqa_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown keys in [pqa] raise — silent ignore is the same data-corruption class."""
    for var in (
        "PQA_BRANCHES",
        "PQA_VERIFY_TESTS",
        "PQA_MODEL",
        "PQA_RUN_BUDGET_USD",
        "PQA_MEMORY_DB",
    ):
        monkeypatch.delenv(var, raising=False)
    toml = _write_raw_toml(
        tmp_path / "pqa-config.toml",
        '[pqa]\nbranches = 3\nverify_tests = false\nmodel = "opus"\n'
        'run_budget_usd = 15.0\nmemory_db = ".db"\nverifie_tests = true\n',  # typo
    )
    # B017 disabled: the locked contract intentionally leaves error-type unpinned —
    # branches may raise TypeError, ValueError, a custom ConfigError, or anything else;
    # only the fact that load_config raises is locked.
    with pytest.raises(Exception):  # noqa: B017
        load_config(toml)


def test_load_config_partial_toml_uses_defaults_for_missing_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TOML with only `model` set → other fields are defaults from config/settings.py.
    Partial config is not an error; only unknown keys are. Defaults from settings.py:
    branches=3, verify_tests=False, model='opus', run_budget_usd=15.0,
    memory_db='.claude/hooks/memory/pqa_memory.db'.
    """
    for var in (
        "PQA_BRANCHES",
        "PQA_VERIFY_TESTS",
        "PQA_MODEL",
        "PQA_RUN_BUDGET_USD",
        "PQA_MEMORY_DB",
    ):
        monkeypatch.delenv(var, raising=False)
    toml = _write_raw_toml(tmp_path / "pqa-config.toml", '[pqa]\nmodel = "haiku"\n')
    cfg = load_config(toml)
    assert cfg.model == "haiku"
    assert cfg.branches == 3
    assert cfg.verify_tests is False
    assert cfg.run_budget_usd == pytest.approx(15.0)
    assert cfg.memory_db == ".claude/hooks/memory/pqa_memory.db"


def test_load_config_rejects_non_finite_run_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inf/nan smuggle past `float()` parsing and would bypass cost-tracker budgets.
    Both PQA_RUN_BUDGET_USD=inf and PQA_RUN_BUDGET_USD=nan must raise at load time."""
    for var in ("PQA_BRANCHES", "PQA_VERIFY_TESTS", "PQA_MODEL", "PQA_MEMORY_DB"):
        monkeypatch.delenv(var, raising=False)
    toml = _write_toml(tmp_path / "pqa-config.toml")
    for bad in ("inf", "-inf", "nan", "Infinity"):
        monkeypatch.setenv("PQA_RUN_BUDGET_USD", bad)
        with pytest.raises(Exception):  # noqa: B017
            load_config(toml)


def test_load_config_rejects_non_positive_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """branches must be >= 1 — 0 and negatives are not a valid superposition.
    Domain validation closes the gap between Python-type-correct and
    semantically-correct: branches=0 passes isinstance(int) but cannot run."""
    for var in (
        "PQA_BRANCHES",
        "PQA_VERIFY_TESTS",
        "PQA_MODEL",
        "PQA_RUN_BUDGET_USD",
        "PQA_MEMORY_DB",
    ):
        monkeypatch.delenv(var, raising=False)
    for bad in (0, -1, -100):
        toml = _write_toml(tmp_path / "pqa-config.toml", branches=bad)
        with pytest.raises(Exception):  # noqa: B017
            load_config(toml)


def test_load_config_rejects_negative_run_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_budget_usd must be > 0 — Budget dataclass enforces it; load_config
    should fail fast at the boundary, not let invalid values flow downstream."""
    for var in (
        "PQA_BRANCHES",
        "PQA_VERIFY_TESTS",
        "PQA_MODEL",
        "PQA_RUN_BUDGET_USD",
        "PQA_MEMORY_DB",
    ):
        monkeypatch.delenv(var, raising=False)
    for bad in (0.0, -0.01, -100.0):
        toml = _write_toml(tmp_path / "pqa-config.toml", run_budget_usd=bad)
        with pytest.raises(Exception):  # noqa: B017
            load_config(toml)


def test_load_config_translates_non_utf8_to_tomldecodeerror(tmp_path: Path) -> None:
    """Non-UTF8 bytes must chain TOMLDecodeError, same as syntactically-malformed
    TOML. Leaking a raw UnicodeDecodeError bypasses the round-1 contract pin."""
    toml = tmp_path / "pqa-config.toml"
    # Latin-1 encoded bytes that are not valid UTF-8 (0xC3 followed by 0x28 is invalid).
    toml.write_bytes(b'[pqa]\nmodel = "\xc3\x28"\n')
    with pytest.raises(Exception) as exc_info:
        load_config(toml)
    chain: list[BaseException] = []
    current: BaseException | None = exc_info.value
    while current is not None:
        chain.append(current)
        current = current.__cause__ or current.__context__
    assert any(isinstance(exc, tomllib.TOMLDecodeError) for exc in chain), (
        f"non-UTF8 TOML must chain TOMLDecodeError; got {[type(e).__name__ for e in chain]}"
    )


def test_load_config_directory_path_raises_clearly(tmp_path: Path) -> None:
    """Passing a directory path must raise a clear error, not leak raw
    IsADirectoryError. The contract for `not a usable file` is broader than
    `missing file` — a path-shape error must surface explicitly."""
    with pytest.raises(Exception) as exc_info:
        load_config(tmp_path)  # tmp_path is a directory, not a file
    # The error must mention the path or its directory-ness so callers can debug.
    text = str(exc_info.value).lower()
    assert "director" in text or "not a regular file" in text or "is a directory" in text, (
        f"directory-path error must surface the cause; got: {exc_info.value!r}"
    )


def test_load_config_invalid_env_value_raises_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PQA_BRANCHES='three' (env value not parseable as int) → raises at load_config time,
    not later at consumer attribute access. The error must mention the env var name OR
    chain a ValueError so the user can find the cause."""
    monkeypatch.setenv("PQA_BRANCHES", "three")
    toml = _write_toml(tmp_path / "pqa-config.toml")
    with pytest.raises(Exception) as exc_info:
        load_config(toml)
    text = (
        f"{exc_info.value}".lower()
        + " "
        + " ".join(
            str(e).lower() for e in (exc_info.value.__cause__, exc_info.value.__context__) if e
        )
    )
    assert (
        "pqa_branches" in text
        or "branches" in text
        or "valueerror" in text
        or "value error" in text
    ), f"invalid-env error must name the failing var or chain ValueError; got: {exc_info.value!r}"
