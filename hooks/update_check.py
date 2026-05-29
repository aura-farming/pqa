#!/usr/bin/env python3
"""SessionStart hook. Print a one-line banner when a newer PQA release exists.

This is the plugin-ownable equivalent of an "update available" indicator: the
status line is a single global setting (often owned by another plugin), but every
plugin's SessionStart hook runs, so this is where PQA can surface an update notice
without conflicting.

Design constraints (match the other PQA hooks):
  - Never blocks a session (always exit 0).
  - Stdlib only.
  - The network check is cached for 24h and times out fast, so at most one GitHub
    request per day; everything fails SILENT (offline, rate-limited, or a GitHub
    API change => no banner, never an error in the user's face).

Installed version is read from `PQA_VERSION` next to this file — it ships in both
the plugin install (CLAUDE_PLUGIN_ROOT/hooks/) and the manual install (.claude/hooks/).
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

REPO = "aura-farming/pqa"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
CACHE_TTL_SECONDS = 24 * 60 * 60
_NETWORK_TIMEOUT_SECONDS = 2.0
_CACHE_PATH = Path.home() / ".cache" / "pqa" / "update_check.json"


def parse_version(raw: str | None) -> tuple[int, ...] | None:
    """Parse 'v0.2.5' / '0.2.5' into (0, 2, 5). None if any component is non-numeric."""
    if not raw:
        return None
    stripped = raw.strip().lstrip("vV")
    try:
        return tuple(int(part) for part in stripped.split("."))
    except ValueError:
        return None


def is_newer(latest: str, installed: str) -> bool:
    """True iff `latest` is a strictly higher version than `installed`. Fails closed
    (False) when either side is unparseable, so a bad value never nags the user."""
    latest_v, installed_v = parse_version(latest), parse_version(installed)
    if latest_v is None or installed_v is None:
        return False
    return latest_v > installed_v


def read_installed_version(version_file: Path) -> str | None:
    try:
        return version_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def format_banner(latest: str, installed: str) -> str:
    return (
        f"⬆️  PQA {latest} available — you have {installed}.\n"
        "   Update: /plugin   (or: git pull && ./scripts/install.sh)"
    )


def compute_banner(installed: str | None, latest: str | None) -> str | None:
    """The banner string to print, or None to stay silent."""
    if not installed or not latest:
        return None
    return format_banner(latest, installed) if is_newer(latest, installed) else None


def _fetch_latest_version() -> str | None:
    """GET the latest release tag from GitHub. None on any failure (fail-silent)."""
    # Defence-in-depth for the S310 lint: the endpoint is a fixed https constant, never
    # user input, so no file:/custom scheme can reach urlopen — assert it explicitly.
    if not LATEST_RELEASE_URL.startswith("https://"):
        return None
    request = urllib.request.Request(  # noqa: S310 - fixed https endpoint, scheme checked above
        LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "pqa-update-check"},
    )
    # NOTE: separate single-type except clauses, NOT `except (OSError, ValueError)`.
    # ruff 0.15 `format` with target py314 corrupts except-tuples into invalid Python
    # (`except A, B:`). URLError/TimeoutError are OSError subclasses; JSON/decode errors
    # are ValueError subclasses, so two clauses cover every failure mode here.
    try:
        with urllib.request.urlopen(request, timeout=_NETWORK_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload: Any = json.loads(response.read().decode("utf-8"))
    except OSError:
        return None
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    tag = cast("dict[str, Any]", payload).get("tag_name")
    return tag if isinstance(tag, str) else None


def _read_fresh_cache(cache_path: Path, now: float) -> str | None:
    """Cached latest version if the cache exists and is within the TTL, else None."""
    try:
        raw: Any = json.loads(cache_path.read_text(encoding="utf-8"))
    except OSError:  # see _fetch_latest_version: split clauses dodge the ruff-format tuple bug
        return None
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    cached = cast("dict[str, Any]", raw)
    checked_at, latest = cached.get("checked_at"), cached.get("latest")
    if not isinstance(checked_at, (int, float)) or not isinstance(latest, str):
        return None
    return latest if now - checked_at <= CACHE_TTL_SECONDS else None


def _write_cache(cache_path: Path, latest: str, now: float) -> None:
    # cache is best-effort; a write failure just means we re-check next session
    with contextlib.suppress(OSError):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"checked_at": now, "latest": latest}), encoding="utf-8")


def latest_version(
    cache_path: Path, now: float, fetch: Callable[[], str | None] = _fetch_latest_version
) -> str | None:
    """Latest release version, served from cache when fresh and only hitting the
    network when the cache is stale or missing."""
    cached = _read_fresh_cache(cache_path, now)
    if cached is not None:
        return cached
    fetched = fetch()
    if fetched is not None:
        _write_cache(cache_path, fetched, now)
    return fetched


def main() -> int:
    with contextlib.suppress(OSError):
        sys.stdin.read()  # drain the SessionStart payload; we don't need it
    installed = read_installed_version(Path(__file__).resolve().parent / "PQA_VERSION")
    latest = latest_version(_CACHE_PATH, time.time())
    banner = compute_banner(installed, latest)
    if banner:
        print(banner)
    return 0  # never block a session on an update check


if __name__ == "__main__":
    sys.exit(main())
