#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit) verification loop.

The honesty spine. After every code edit it lints the changed file, and — when
PQA_VERIFY_TESTS=1 — runs the suite. Failures exit 2, feeding the error back to the
model so it must address them before moving on. Stdlib only.

Default is lint-only (fast, <200ms-ish) so the loop doesn't drag every edit. Tests
are opt-in per session because a full suite after every edit is slow on big repos;
turn them on for the collapse phase.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def read_payload() -> dict[str, Any]:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def changed_path(payload: dict[str, Any]) -> str | None:
    tool_input: dict[str, Any] = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path")
    return str(path) if path else None


def _safe_cwd(payload: dict[str, Any]) -> str:
    """Validate `cwd` before passing it to subprocess. A crafted payload pointing at
    /tmp/evil would otherwise let ruff/pytest pick up a malicious pyproject.toml or
    pytest plugin from there. Trust `cwd` only if it resolves to an existing directory;
    otherwise fall back to the process's own cwd (set by the hook runner, not by the
    payload)."""
    raw = payload.get("cwd")
    if isinstance(raw, str) and raw:
        candidate = Path(raw)
        try:
            if candidate.is_dir():
                return str(candidate)
        except OSError:
            pass
    return str(Path.cwd())


def run(cmd: list[str], cwd: str) -> tuple[int, str]:
    try:
        # ruff/pytest are project-controlled tool names from the hook itself, not user input.
        proc = subprocess.run(  # noqa: S603 — tool list is hook-controlled, not external input
            cmd, cwd=cwd, capture_output=True, text=True, timeout=110
        )
        return proc.returncode, (proc.stdout + proc.stderr)
    except FileNotFoundError:
        return 0, ""  # tool not installed → skip silently, don't fail the edit
    except subprocess.TimeoutExpired:
        return 1, "verification timed out"


def main() -> int:
    payload = read_payload()
    cwd = _safe_cwd(payload)
    path = changed_path(payload)
    if not path or not path.endswith(".py"):
        return 0
    if not Path(path).exists():
        return 0

    problems: list[str] = []

    # `--` end-of-options separator: ensures a path beginning with `-` is treated as a
    # path, not as a ruff flag. Defense-in-depth — `path` is already validated to exist.
    lint_rc, lint_out = run(["ruff", "check", "--", path], cwd)
    if lint_rc != 0 and lint_out.strip():
        problems.append(f"ruff:\n{lint_out.strip()}")

    if os.getenv("PQA_VERIFY_TESTS") == "1":
        test_rc, test_out = run(["pytest", "-q"], cwd)
        if test_rc != 0 and test_out.strip():
            problems.append(f"pytest:\n{test_out.strip()[-2000:]}")

    if not problems:
        return 0
    sys.stderr.write(
        "PQA verify loop found problems in the change you just made:\n\n"
        + "\n\n".join(problems)
        + "\n\nFix these before continuing. Verification is the collapse gate — "
        "an edit that fails it has not been accepted.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
