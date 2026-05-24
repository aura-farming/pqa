#!/usr/bin/env python3
"""PreToolUse(Bash) gate. Blocks destructive and exfiltration commands.

This is the one layer no branch can override. Reads the Claude Code hook payload
from stdin; exit code 2 blocks the command and feeds the reason back to the model.
Stdlib only. Fails open on parse errors (never block on a malformed payload), but
fails closed on any matched dangerous pattern.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# (pattern, human reason). Patterns are intentionally conservative and specific.
DANGEROUS: list[tuple[str, str]] = [
    (r"\brm\s+-rf\s+(/|~|\$HOME)(\s|$)", "recursive delete of a root/home path"),
    (r"\bgit\s+push\b.*--force.*\b(main|master)\b", "force-push to a protected branch"),
    (r"\bgit\s+push\s+--force(?!-with-lease)", "blind force-push (use --force-with-lease)"),
    (r"(curl|wget)\s+[^|]*\|\s*(sudo\s+)?(sh|bash|zsh)", "pipe-to-shell of remote content"),
    (r"(curl|wget)\b[^\n]*(-d|--data|-T|--upload-file)[^\n]*\.env", "exfiltration of .env"),
    (
        r"\b(cat|cp|scp|curl|wget)\b[^\n]*(\.env|id_rsa|\.pem|credentials)",
        "access to a secret/key file",
    ),
    (r"\bchmod\s+-R?\s*777\b", "world-writable permissions"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", "fork bomb"),
    (r"\bdd\b[^\n]*of=/dev/(sd|nvme|disk)", "raw write to a block device"),
    (r">\s*/dev/(sd|nvme|disk)", "raw write to a block device"),
]


def read_payload() -> dict[str, Any]:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def extract_command(payload: dict[str, Any]) -> str:
    tool_input: dict[str, Any] = payload.get("tool_input") or {}
    return str(tool_input.get("command", ""))


def find_violation(command: str) -> str | None:
    for pattern, reason in DANGEROUS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return reason
    return None


def main() -> int:
    command = extract_command(read_payload())
    if not command:
        return 0
    reason = find_violation(command)
    if reason is None:
        return 0
    sys.stderr.write(
        f"PQA security gate blocked this command: {reason}.\n"
        "This gate cannot be disabled to proceed. Find a safe alternative — "
        "for example, scope deletes to the repo, use --force-with-lease, "
        "download then inspect before executing, and never read or transmit secrets.\n"
    )
    return 2  # exit 2 → Claude Code cancels the command and shows stderr to the model


if __name__ == "__main__":
    sys.exit(main())
