#!/usr/bin/env python3
"""PreToolUse(Read) gate. Blocks any subagent from reading secret material.

Generators, adversaries, and verifiers all hold the Read tool, and worktrees share the
repo — so without this, a branch could read .env or a key file straight into a prompt.
Exit code 2 blocks the read and tells the model why. Stdlib only.

Hardened against:
  - relative paths (`subdir/../.env` resolves to `.env`)
  - symlinks (a benign-named file linked at a secret)
  - parent-directory traversal
  - case variation (`.ENV`, `Id_Rsa`)
  - missing/non-dict payloads (fail closed)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

SECRET_PATHS = re.compile(
    r"(^|/)(\.env(\.(?!example\b|sample\b|template\b|dist\b)[a-z0-9_-]+|$)|"
    r"id_rsa|id_ed25519|.*\.pem|.*\.key|credentials|\.netrc|"
    r"\.aws/|\.ssh/|secrets?\.(ya?ml|json|toml))",
    re.IGNORECASE,
)


def read_payload() -> dict[str, Any] | None:
    """Fail-closed on malformed input. None means 'block this read.'"""
    try:
        parsed: Any = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, Any]", parsed)


def target_path(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    raw: Any = (
        cast("dict[str, Any]", tool_input).get("file_path")
        or cast("dict[str, Any]", tool_input).get("path")
        or ""
    )
    return raw if isinstance(raw, str) else ""


def _normalised_candidates(raw_path: str) -> list[str]:
    """Return every string we need to match against the secret-paths regex.

    The original guard checked only the raw string from the payload. That misses:
      - `subdir/../.env` (resolves to `.env` after normalisation)
      - `./.env` (the leading `./` doesn't match the `(^|/)` anchor cleanly)
      - symlinks: a path like `notes.txt` that resolves through readlink to `~/.env`
      - case variation: regex is already case-insensitive, but `Path.resolve()`
        may surface a different casing on case-preserving filesystems

    We check the raw path, the lexically normalised path (without resolving symlinks),
    and the symlink-resolved path. Any one matching the secret regex blocks.
    """
    candidates: list[str] = []
    if not raw_path:
        return candidates
    candidates.append(raw_path)

    p = Path(raw_path)

    # Lexical normalisation — collapses `..` and `.` without touching the filesystem,
    # so a traversal-encoded payload (`a/../.env`) reveals its real target.
    try:
        lexical = str(Path(*p.parts))  # rebuilds parts; .resolve(strict=False) below handles ..
        # os.path.normpath would be cleaner but Path is stdlib-idiomatic.
        import os

        lexical_norm = os.path.normpath(raw_path)
        if lexical_norm not in candidates:
            candidates.append(lexical_norm)
        if lexical not in candidates:
            candidates.append(lexical)
    except OSError:
        pass
    except ValueError:
        pass

    # Resolve symlinks. We do this best-effort: if the file does not exist, resolve()
    # still yields the would-be path which is what we want to check.
    try:
        resolved = str(p.resolve(strict=False))
        if resolved not in candidates:
            candidates.append(resolved)
    except OSError:
        # symlink loops or missing parents — we keep the raw path in candidates
        # so the regex check still fires on whatever pattern the attacker tried.
        pass
    except RuntimeError:
        # RuntimeError can occur on infinite symlink loops; treat as suspicious
        # and rely on the raw-path check.
        pass

    return candidates


def main() -> int:
    payload = read_payload()
    if payload is None:
        sys.stderr.write(
            "PQA secrets guard: payload did not parse to a dict. Blocking fail-closed.\n"
        )
        return 2

    raw = target_path(payload)
    if not raw:
        return 0

    for candidate in _normalised_candidates(raw):
        if SECRET_PATHS.search(candidate):
            sys.stderr.write(
                f"PQA secrets guard blocked a read of '{raw}'"
                + (f" (resolves to '{candidate}')" if candidate != raw else "")
                + ". Subagents must never load secret material into a prompt or a branch. "
                "Reference secrets via environment variables at runtime instead; never read "
                "the file directly.\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
