#!/usr/bin/env python3
"""UserPromptSubmit gate. On substantial build-intent prompts, injects a SHORT pointer
to the PQA loop — once per session — so the model considers dual-frame loading and /pqa
without paying a recurring context tax.

Context discipline (roadmap §4.2): the old gate fired on nearly every coding prompt
("add", "fix", "write" are unavoidable words) and repeated a ~110-token protocol every
time. This version:
  - two-tier intent: strong build verbs fire at any length; weak verbs (create/add/
    fix/write) only fire on substantial prompts (>= 12 words), so "fix typo" stays
    silent;
  - explicit slash-command matching (the old `\\b/pqa\\b` alternative could never match
    at prompt start — \\b needs a word char before `/`);
  - fires ONCE per session, tracked in <cwd>/.pqa/research_gate.state;
  - honours PQA_DISABLED_HOOKS=research_gate.

Soft gate: stdout is added to context; never blocks; always exits 0. Stdlib only.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from hook_common import is_disabled

STRONG_INTENT = re.compile(
    r"\b(build|implement|design|architect|refactor|rewrite|optimi[sz]e|solve)\b",
    re.IGNORECASE,
)
WEAK_INTENT = re.compile(r"\b(create|add|fix|write)\b", re.IGNORECASE)
SLASH_COMMAND = re.compile(r"(?:^|\s)/(?:pqa|superpose|frame|collapse)\b", re.IGNORECASE)
WEAK_INTENT_MIN_WORDS = 12

PROTOCOL = (
    "[PQA] Build task detected — consider the loop: load the dual-frame (research vs "
    "self-eval), then /pqa to superpose divergent branches, collide, and collapse on "
    "verifier evidence. Conviction protects exploration, never acceptance.\n"
    "(Fires once per session. Disable: PQA_DISABLED_HOOKS=research_gate.)"
)


def read_payload() -> dict[str, Any]:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def wants_protocol(prompt: str) -> bool:
    """Two-tier intent match. Strong verbs and explicit slash-commands always fire;
    weak verbs need a substantial prompt — a trivial ask should not buy a
    multi-branch protocol pitch."""
    if SLASH_COMMAND.search(prompt) or STRONG_INTENT.search(prompt):
        return True
    return bool(WEAK_INTENT.search(prompt)) and len(prompt.split()) >= WEAK_INTENT_MIN_WORDS


def _state_path(payload: dict[str, Any]) -> Path | None:
    """Per-project state file. Trust cwd only if it is an existing directory (same
    rule as the other hooks); without a session_id there is nothing to track."""
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        return None
    raw_cwd = payload.get("cwd")
    base = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    try:
        if not base.is_dir():
            return None
    except OSError:
        return None
    return base / ".pqa" / "research_gate.state"


def already_fired(state: Path | None, session: str) -> bool:
    if state is None:
        return False
    try:
        return state.read_text(encoding="utf-8").strip() == session
    except OSError:
        return False


def mark_fired(state: Path | None, session: str) -> None:
    if state is None:
        return
    with contextlib.suppress(OSError):
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(session, encoding="utf-8")


def main() -> int:
    if is_disabled("research_gate"):
        return 0
    payload = read_payload()
    prompt = str(payload.get("prompt", ""))
    if not wants_protocol(prompt):
        return 0
    session = str(payload.get("session_id", ""))
    state = _state_path(payload)
    if already_fired(state, session):
        return 0
    with contextlib.suppress(BrokenPipeError):
        print(PROTOCOL)
    mark_fired(state, session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
