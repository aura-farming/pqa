"""Locked behaviour contract for pqa.config.load_config.

These tests describe the minimum surface every PQA superposition branch must
satisfy. They were committed to the branches' base ref before the orchestrator
spawned generators — branches that author or modify these tests are flagged
as critical anomalies and excluded from collapse.

Behaviour pinned here:
    1. `from pqa.config import load_config` is the canonical entry point.
    2. load_config(path) returns an object exposing the five PQA settings
       (branches, verify_tests, model, run_budget_usd, memory_db) with the
       types config/settings.py declares.
    3. The returned object is immutable (frozen) — mutating an attribute raises.
    4. A malformed TOML raises an exception that chains tomllib.TOMLDecodeError;
       silent acceptance of broken TOML is forbidden.
    5. The loader accepts both str and pathlib.Path for the file argument.

Behaviour deliberately NOT pinned (branches differ on these — the adversary
attacks the differences):
    - Whether env vars participate, and if so what precedence they take vs TOML.
    - Whether the loader returns defaults or raises when the file is absent.
    - Whether unknown TOML keys raise, warn, or are silently ignored.
    - The exact internal module path of the loader — only `pqa.config.load_config`
      is locked as a public symbol.
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
