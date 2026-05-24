#!/usr/bin/env python3
"""PreToolUse(Read) gate. Blocks any subagent from reading secret material.

Generators, adversaries, and verifiers all hold the Read tool, and worktrees share the
repo — so without this, a branch could read .env or a key file straight into a prompt.
Exit code 2 blocks the read and tells the model why. Stdlib only; fails open on parse
errors, closed on a matched secret path.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

SECRET_PATHS = re.compile(
    r"(^|/)(\.env(\.|$)|id_rsa|id_ed25519|.*\.pem|.*\.key|credentials|\.netrc|"
    r"\.aws/|\.ssh/|secrets?\.(ya?ml|json|toml))",
    re.IGNORECASE,
)


def read_payload() -> dict[str, Any]:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def target_path(payload: dict[str, Any]) -> str:
    tool_input: dict[str, Any] = payload.get("tool_input") or {}
    return str(tool_input.get("file_path") or tool_input.get("path") or "")


def main() -> int:
    path = target_path(read_payload())
    if path and SECRET_PATHS.search(path):
        sys.stderr.write(
            f"PQA secrets guard blocked a read of '{path}'. Subagents must never load secret "
            "material into a prompt or a branch. Reference secrets via environment variables at "
            "runtime instead; never read the file directly.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
