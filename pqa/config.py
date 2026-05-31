"""PQA configuration loader — stdlib-conservative branch (b0).

Topology:
    - `_DEFAULTS` is owned by this module (no import-time read of env from
      `config/settings.py`; that module's eager `os.getenv` was the round-1
      trap that produced an env-at-import data-corruption class).
    - Errors are builtin: `TypeError` for wrong-typed values, `ValueError`
      for invalid env / unknown keys / failed coercion, `FileNotFoundError`
      for missing file. Real causes are chained with `raise X(...) from cause`.
    - Validation is an explicit `isinstance` ladder per field — no spec dict,
      no declarative table. Every field's type rule is hand-written for
      auditability (the tightened contract names this as the data-integrity
      surface).
    - The result is a frozen dataclass — mutation raises ``FrozenInstanceError``
      (a subclass of ``AttributeError``).
    - Precedence in one pass: defaults → TOML overrides → env overrides.
      Each layer validates only the keys it actually contributes.
"""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

# ---------------------------------------------------------------------------
# Loader-owned defaults. The values mirror config/settings.py but the source
# is THIS module so we do not inherit `os.getenv`-at-import semantics from it.
# Mapping is created once at module import and never mutated.
_DEFAULTS: Final[dict[str, int | bool | str | float]] = {
    "branches": 3,
    "verify_tests": False,
    "model": "opus",
    "run_budget_usd": 15.0,
    "memory_db": ".claude/hooks/memory/pqa_memory.db",
}

# The full set of valid [pqa] keys. Anything else is a typo / unknown key.
_KNOWN_KEYS: Final[frozenset[str]] = frozenset(_DEFAULTS.keys())

# The allowlist of valid `model` values: the short aliases an operator sets in config.
# NOTE: this is a declared *preference* only. Phase 0 dispatch and cost accounting use
# the concrete `claude-*` key carried on each Branch (Branch.model / orchestrator
# _DEFAULT_MODEL), NOT this field — there is no alias->pricing translation yet, and
# cost.MODEL_PRICING is keyed on the concrete names. Before wiring cfg.model into a
# Branch, add an alias->concrete map: these aliases are disjoint from the pricing keys,
# so an unmapped alias would KeyError in cost_for at record time.
_VALID_MODELS: Final[frozenset[str]] = frozenset({"opus", "sonnet", "haiku"})

# Mapping from PQA_* env var name to TOML key.
_ENV_MAP: Final[dict[str, str]] = {
    "PQA_BRANCHES": "branches",
    "PQA_VERIFY_TESTS": "verify_tests",
    "PQA_MODEL": "model",
    "PQA_RUN_BUDGET_USD": "run_budget_usd",
    "PQA_MEMORY_DB": "memory_db",
}


@dataclass(frozen=True, slots=True)
class PQAConfig:
    """Immutable PQA settings. Mutation raises ``FrozenInstanceError``."""

    branches: int
    verify_tests: bool
    model: str
    run_budget_usd: float
    memory_db: str


# ---------------------------------------------------------------------------
# Per-field validators. Each is a small isinstance ladder; chosen for
# auditability over abstraction. `bool` is a subclass of `int` in Python, so
# `branches` and `run_budget_usd` must reject `bool` explicitly.


def _validate_branches(value: object, *, origin: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"{origin}: 'branches' must be int, got {type(value).__name__}={value!r}",
        )
    if value < 1:
        raise ValueError(
            f"{origin}: 'branches' must be >= 1, got {value}",
        )
    return value


def _validate_verify_tests(value: object, *, origin: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(
            f"{origin}: 'verify_tests' must be bool, got {type(value).__name__}={value!r}",
        )
    return value


def _validate_model(value: object, *, origin: str) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{origin}: 'model' must be str, got {type(value).__name__}={value!r}",
        )
    if value not in _VALID_MODELS:
        raise ValueError(
            f"{origin}: 'model' must be one of {sorted(_VALID_MODELS)}, got {value!r}",
        )
    return value


def _validate_run_budget_usd(value: object, *, origin: str) -> float:
    if isinstance(value, bool):
        raise TypeError(
            f"{origin}: 'run_budget_usd' must be float, got bool={value!r}",
        )
    if isinstance(value, int | float):
        as_float = float(value)
        if not math.isfinite(as_float):
            raise ValueError(
                f"{origin}: 'run_budget_usd' must be finite, got {as_float!r} "
                "(inf/nan would bypass the cost-tracker budget gate)",
            )
        if as_float <= 0:
            raise ValueError(
                f"{origin}: 'run_budget_usd' must be > 0, got {as_float!r}",
            )
        return as_float
    raise TypeError(
        f"{origin}: 'run_budget_usd' must be float, got {type(value).__name__}={value!r}",
    )


_DANGEROUS_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "/etc/",
    "/usr/",
    "/var/",
    "/sys/",
    "/proc/",
    "/dev/",
    "/boot/",
    "/root/",
    "/bin/",
    "/sbin/",
    "/lib/",
    "/lib64/",
    "/System/",
)


def _validate_memory_db(value: object, *, origin: str) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{origin}: 'memory_db' must be str, got {type(value).__name__}={value!r}",
        )
    if not value.strip():
        raise ValueError(
            f"{origin}: 'memory_db' must be a non-empty path",
        )
    # POSIX-only sanity guard: refuse to create / overwrite sqlite files in system
    # directories. Catches accidental fat-finger / stale env from another project,
    # not adversarial use (the trust model is a developer's own machine). Windows
    # paths don't match these prefixes so the check is a no-op there.
    absolute = str(Path(value).expanduser().absolute())
    for prefix in _DANGEROUS_PATH_PREFIXES:
        if absolute.startswith(prefix):
            raise ValueError(
                f"{origin}: 'memory_db' resolves into a system directory ({absolute}); "
                "use a path under your project or home directory",
            )
    return value


# ---------------------------------------------------------------------------
# Env coercion. Each PQA_* env var arrives as a string; coerce to the field's
# native type. Failures raise a clear ValueError naming the env var and chain
# the underlying parse error via __cause__.


def _coerce_env_branches(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as cause:
        raise ValueError(
            f"PQA_BRANCHES must be an integer, got {raw!r}",
        ) from cause


def _coerce_env_verify_tests(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"PQA_VERIFY_TESTS must be a boolean (0/1, true/false), got {raw!r}",
    )


def _coerce_env_run_budget_usd(raw: str) -> float:
    try:
        return float(raw)
    except ValueError as cause:
        raise ValueError(
            f"PQA_RUN_BUDGET_USD must be a float, got {raw!r}",
        ) from cause


def _coerce_env_value(key: str, raw: str) -> int | bool | str | float:
    if key == "branches":
        return _coerce_env_branches(raw)
    if key == "verify_tests":
        return _coerce_env_verify_tests(raw)
    if key == "run_budget_usd":
        return _coerce_env_run_budget_usd(raw)
    # model and memory_db are already strings — no coercion.
    return raw


# ---------------------------------------------------------------------------
# Stage helpers — each is small and single-purpose.


def _read_toml(path: Path) -> dict[str, object]:
    """Read and parse the TOML file. Chain TOMLDecodeError and FileNotFoundError.

    Path-shape errors surface explicitly:
        - Missing path                 -> FileNotFoundError
        - Path exists but is not a file -> IsADirectoryError
        - Path exists but unreadable    -> chained FileNotFoundError

    Encoding errors translate to TOMLDecodeError so the locked-contract pin
    (malformed-file chains TOMLDecodeError) holds for non-UTF8 inputs too.
    """
    if not path.exists():
        raise FileNotFoundError(f"PQA config file not found: {path}")
    if not path.is_file():
        raise IsADirectoryError(
            f"PQA config path is not a regular file (got a directory): {path}",
        )
    try:
        raw = path.read_bytes()
    except OSError as cause:
        raise FileNotFoundError(
            f"PQA config file unreadable: {path}",
        ) from cause
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as cause:
        # Python 3.14 requires the keyword form for TOMLDecodeError.
        raise tomllib.TOMLDecodeError(
            msg=f"PQA config file is not valid UTF-8: {path}",
            doc="",
            pos=cause.start,
        ) from cause
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as cause:
        raise ValueError(
            f"PQA config file is not valid TOML: {path}",
        ) from cause
    pqa_section: object = parsed.get("pqa", {})
    if not isinstance(pqa_section, dict):
        raise TypeError(
            f"{path}: [pqa] section must be a table, got {type(pqa_section).__name__}",
        )
    return cast("dict[str, object]", pqa_section)


def _reject_unknown_keys(section: dict[str, object], *, path: Path) -> None:
    """Raise ValueError naming the first unknown key. Silent ignore is data corruption."""
    unknown = sorted(set(section.keys()) - _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{path}: unknown key(s) in [pqa]: {', '.join(unknown)}. "
            f"Known keys: {', '.join(sorted(_KNOWN_KEYS))}",
        )


def _collect_env_overrides() -> dict[str, int | bool | str | float]:
    """Read PQA_* env vars and coerce each to its native type."""
    overrides: dict[str, int | bool | str | float] = {}
    for env_name, key in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        overrides[key] = _coerce_env_value(key, raw)
    return overrides


def _validate_field(key: str, value: object, *, origin: str) -> int | bool | str | float:
    """Dispatch to the per-field validator. Explicit ladder by design."""
    if key == "branches":
        return _validate_branches(value, origin=origin)
    if key == "verify_tests":
        return _validate_verify_tests(value, origin=origin)
    if key == "model":
        return _validate_model(value, origin=origin)
    if key == "run_budget_usd":
        return _validate_run_budget_usd(value, origin=origin)
    if key == "memory_db":
        return _validate_memory_db(value, origin=origin)
    # Should never reach here — _reject_unknown_keys runs before us.
    raise KeyError(f"unknown config key: {key!r}")


# ---------------------------------------------------------------------------
# Public entry point.


def load_config(path: str | Path) -> PQAConfig:
    """Load PQA configuration from a TOML file with env overrides.

    Precedence: PQA_* env vars > [pqa] TOML table > built-in defaults.

    Raises:
        FileNotFoundError: the named TOML file does not exist (chained).
        ValueError: malformed TOML (chains TOMLDecodeError), unknown [pqa]
            key, or invalid env value (PQA_* parse failure chains ValueError).
        TypeError: wrong-typed TOML or env value for a field.

    Returns:
        Frozen ``PQAConfig`` — attribute assignment raises ``FrozenInstanceError``.
    """
    toml_path = Path(path)
    section = _read_toml(toml_path)
    _reject_unknown_keys(section, path=toml_path)
    env_overrides = _collect_env_overrides()

    resolved: dict[str, int | bool | str | float] = dict(_DEFAULTS)
    for key, value in section.items():
        resolved[key] = _validate_field(key, value, origin=str(toml_path))
    for key, value in env_overrides.items():
        # env values came through coercion → still re-run the structural
        # validator so the precedence layer cannot smuggle a bad type past us.
        resolved[key] = _validate_field(key, value, origin=f"env:{_env_name_for(key)}")

    return PQAConfig(
        branches=int(resolved["branches"]),
        verify_tests=bool(resolved["verify_tests"]),
        model=str(resolved["model"]),
        run_budget_usd=float(resolved["run_budget_usd"]),
        memory_db=str(resolved["memory_db"]),
    )


def _env_name_for(key: str) -> str:
    """Reverse-lookup the PQA_* env name for a field key (diagnostic-only)."""
    for env_name, mapped in _ENV_MAP.items():
        if mapped == key:
            return env_name
    return f"PQA_{key.upper()}"


def _build_defaults_with_env() -> PQAConfig:
    """Construct a PQAConfig from defaults + PQA_* env overrides, no TOML.

    Used by load_or_defaults() when no TOML file is present. Goes through the
    same per-field validators as the TOML path so the same domain rules apply.
    """
    resolved: dict[str, int | bool | str | float] = dict(_DEFAULTS)
    for key, value in _collect_env_overrides().items():
        resolved[key] = _validate_field(key, value, origin=f"env:{_env_name_for(key)}")
    return PQAConfig(
        branches=int(resolved["branches"]),
        verify_tests=bool(resolved["verify_tests"]),
        model=str(resolved["model"]),
        run_budget_usd=float(resolved["run_budget_usd"]),
        memory_db=str(resolved["memory_db"]),
    )


_DEFAULT_CONFIG_PATH: Final[str] = "pqa-config.toml"


def load_or_defaults(path: str | Path | None = None) -> PQAConfig:
    """Load PQA configuration with graceful fallback to defaults + env.

    Behaviour:
        - If ``path`` is ``None``, defaults to ``pqa-config.toml`` in CWD.
        - If the file exists, calls :func:`load_config` (full strict validation).
        - If the file does NOT exist, returns a :class:`PQAConfig` built from
          built-in defaults + ``PQA_*`` env overrides only. No TOML required.

    All other error semantics match :func:`load_config` — malformed TOML, wrong
    types, unknown keys, invalid env values still raise.

    Use this in entry points (``main.py``, CLI shims) where users may or may not
    have a TOML file. Use :func:`load_config` directly when a file is required.
    """
    resolved_path = Path(path) if path is not None else Path(_DEFAULT_CONFIG_PATH)
    if resolved_path.exists():
        return load_config(resolved_path)
    return _build_defaults_with_env()


__all__ = ["PQAConfig", "load_config", "load_or_defaults"]
