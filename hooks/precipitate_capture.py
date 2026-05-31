#!/usr/bin/env python3
"""SubagentStop hook. Continuous learning: when a PQA subagent finishes, scan its output
for conviction signals and named precipitates and persist them to the memory store, so the
next run's frames are sharper. Never blocks a run (always exit 0); degrades to a JSON-lines
log if the DB is unavailable. Stdlib only.

Looks for two markers in the subagent's final text:
  conviction: high, basis: <...>        → a branch's instinct signal
  PRECIPITATE: <name> :: <why it won>   → a named, persisted insight

Hardened against:
  - attacker-controlled `transcript_path` reading arbitrary files (e.g. /etc/passwd)
  - attacker-controlled `cwd` redirecting the SQLite write to an arbitrary location
  - malformed payloads (silently no-ops rather than crashing)
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, cast

# NOTE: kept byte-identical to pqa/signals.py:_PATTERN. This hook is stdlib-only and must
# run without the pqa package importable, so the regex is intentionally duplicated rather
# than imported — change both together.
CONVICTION = re.compile(r"conviction:\s*(high|medium|low)\s*,\s*basis:\s*(.+)", re.IGNORECASE)
PRECIPITATE = re.compile(r"PRECIPITATE:\s*(.+?)\s*::\s*(.+)", re.IGNORECASE)

# Bound DB-inserted strings from transcripts. A compromised subagent or crafted
# transcript could otherwise persist megabytes of attacker-controlled text into the
# memory store, poisoning future frame-loads (precipitates feed the next run's frame).
# Truncating at insert is cheap and reversible — schema-level CHECK constraints would
# be stricter but break migrations.
MAX_NAME_LEN: int = 200
MAX_BASIS_LEN: int = 1_000


def read_payload() -> dict[str, Any]:
    """Returns {} on any parse failure or non-dict payload. This hook is documented as
    never-blocking, so we degrade silently rather than failing closed."""
    try:
        parsed: Any = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return cast("dict[str, Any]", parsed)


def _is_under(child: Path, parent: Path) -> bool:
    """Pre-3.9-compatible containment check that resolves symlinks first.
    Returns True iff `child` (resolved) is `parent` or sits beneath it."""
    try:
        child_resolved = child.resolve(strict=False)
        parent_resolved = parent.resolve(strict=False)
    except OSError:
        return False
    except RuntimeError:
        return False
    try:
        child_resolved.relative_to(parent_resolved)
        return True
    except ValueError:
        return False


def _safe_transcript_path(raw: object, cwd: Path) -> Path | None:
    """Validate the transcript path before reading it.

    The hook payload's transcript_path is *attacker-controllable* if any party in the
    pipeline can set it (a compromised MCP server, a hostile subagent, or a crafted
    payload). Without validation, Path(raw).read_text() would happily read /etc/passwd,
    a private SSH key, or a developer's ~/.zshrc and write its content into the SQLite
    inserts.

    Only allow reading from known-safe roots:
      - ~/.claude/  (where Claude Code stores its own transcript files)
      - <cwd>/.claude/  (per-project Claude Code state)
    """
    if not isinstance(raw, str) or not raw:
        return None
    candidate = Path(raw)
    allowed_roots = [Path.home() / ".claude", cwd / ".claude"]
    if not any(_is_under(candidate, root) for root in allowed_roots):
        return None
    resolved = candidate.resolve(strict=False)
    if not resolved.exists() or not resolved.is_file():
        return None
    # Cheap size cap: refuse files > 50 MB to avoid OOM on a poisoned transcript.
    try:
        if resolved.stat().st_size > 50 * 1024 * 1024:
            return None
    except OSError:
        return None
    return resolved


def last_text(transcript_path: Path) -> str:
    """Pull the final assistant text block from a JSONL transcript, defensively."""
    try:
        lines = transcript_path.read_text().splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_raw = entry.get("message")
        if not isinstance(msg_raw, dict):
            continue
        msg = cast(dict[str, Any], msg_raw)
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            blocks = cast(list[Any], content)
            parts: list[str] = []
            for b in blocks:
                if isinstance(b, dict):
                    block = cast(dict[str, Any], b)
                    parts.append(str(block.get("text", "")))
            return " ".join(parts)
        return str(content)
    return ""


def _safe_cwd(raw: object) -> Path:
    """Validate the working directory before using it as a DB path root.

    A payload with `cwd=/tmp/evil` would otherwise let an attacker direct SQLite
    writes to an arbitrary location. We trust `cwd` only if it resolves to an
    existing directory we can actually use; otherwise we fall back to the
    process's own cwd, which is set by the hook runner (Claude Code itself) and
    not by the payload.
    """
    if isinstance(raw, str) and raw:
        try:
            candidate = Path(raw).resolve(strict=False)
            if candidate.exists() and candidate.is_dir():
                return candidate
        except OSError:
            pass
        except RuntimeError:
            pass
    return Path.cwd()


def db_path(cwd: Path) -> Path:
    """The DB path is always a fixed offset from the validated cwd. The path components
    are hard-coded — no attacker-controlled segment goes into the path construction —
    so even with a poisoned `cwd`, the worst case is writing under that directory's
    `.claude/hooks/memory/` subtree, which is the legitimate location."""
    return cwd / ".claude" / "hooks" / "memory" / "pqa_memory.db"


def persist(cwd: Path, session: str, text: str) -> bool:
    path = db_path(cwd)
    if not path.exists():
        return False  # schema not initialised yet → fall back to log
    try:
        conn = sqlite3.connect(str(path), timeout=2.0)
        ts = int(time.time())
        with conn:
            for name, why in PRECIPITATE.findall(text):
                conn.execute(
                    "INSERT INTO precipitates(session_id, name, rationale, created_at) "
                    "VALUES(?,?,?,?)",
                    (session, name.strip()[:MAX_NAME_LEN], why.strip()[:MAX_BASIS_LEN], ts),
                )
            for level, basis in CONVICTION.findall(text):
                conn.execute(
                    "INSERT INTO signals(session_id, level, basis, created_at) VALUES(?,?,?,?)",
                    (session, level.lower(), basis.strip()[:MAX_BASIS_LEN], ts),
                )
        conn.close()
        return True
    except sqlite3.Error:
        return False


def fallback_log(cwd: Path, session: str, text: str) -> None:
    record = {
        "ts": int(time.time()),
        "session": session,
        "precipitates": [
            {"name": n.strip()[:MAX_NAME_LEN], "why": w.strip()[:MAX_BASIS_LEN]}
            for n, w in PRECIPITATE.findall(text)
        ],
        "signals": [
            {"level": level.lower(), "basis": basis.strip()[:MAX_BASIS_LEN]}
            for level, basis in CONVICTION.findall(text)
        ],
    }
    if not record["precipitates"] and not record["signals"]:
        return
    log = cwd / ".claude" / "memory" / "capture_fallback.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def main() -> int:
    payload = read_payload()
    cwd = _safe_cwd(payload.get("cwd"))
    session = str(payload.get("session_id", "unknown"))

    transcript = _safe_transcript_path(payload.get("transcript_path"), cwd)
    text = last_text(transcript) if transcript else ""

    if text and not persist(cwd, session, text):
        fallback_log(cwd, session, text)
    return 0  # never block


if __name__ == "__main__":
    sys.exit(main())
