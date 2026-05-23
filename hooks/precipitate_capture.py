#!/usr/bin/env python3
"""SubagentStop hook. Continuous learning: when a PQA subagent finishes, scan its output
for conviction signals and named precipitates and persist them to the memory store, so the
next run's frames are sharper. Never blocks a run (always exit 0); degrades to a JSON-lines
log if the DB is unavailable. Stdlib only.

Looks for two markers in the subagent's final text:
  conviction: high, basis: <...>        → a branch's instinct signal
  PRECIPITATE: <name> :: <why it won>   → a named, persisted insight
"""
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

CONVICTION = re.compile(r"conviction:\s*(high|medium|low)\s*,\s*basis:\s*(.+)", re.IGNORECASE)
PRECIPITATE = re.compile(r"PRECIPITATE:\s*(.+?)\s*::\s*(.+)", re.IGNORECASE)


def read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}


def last_text(transcript_path: str) -> str:
    """Pull the final assistant text block from a JSONL transcript, defensively."""
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        msg = entry.get("message", {})
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        return str(content)
    return ""


def db_path(cwd: str) -> Path:
    return Path(cwd) / ".claude" / "hooks" / "memory" / "pqa_memory.db"


def persist(cwd: str, session: str, text: str) -> bool:
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
                    (session, name.strip(), why.strip(), ts),
                )
            for level, basis in CONVICTION.findall(text):
                conn.execute(
                    "INSERT INTO signals(session_id, level, basis, created_at) "
                    "VALUES(?,?,?,?)",
                    (session, level.lower(), basis.strip(), ts),
                )
        conn.close()
        return True
    except sqlite3.Error:
        return False


def fallback_log(cwd: str, session: str, text: str) -> None:
    record = {
        "ts": int(time.time()),
        "session": session,
        "precipitates": [{"name": n.strip(), "why": w.strip()} for n, w in PRECIPITATE.findall(text)],
        "signals": [{"level": l.lower(), "basis": b.strip()} for l, b in CONVICTION.findall(text)],
    }
    if not record["precipitates"] and not record["signals"]:
        return
    log = Path(cwd) / ".claude" / "memory" / "capture_fallback.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def main() -> int:
    payload = read_payload()
    cwd = payload.get("cwd") or os.getcwd()
    session = str(payload.get("session_id", "unknown"))
    text = last_text(str(payload.get("transcript_path", "")))
    if text and not persist(cwd, session, text):
        fallback_log(cwd, session, text)
    return 0  # never block


if __name__ == "__main__":
    sys.exit(main())
