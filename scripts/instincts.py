#!/usr/bin/env python3
"""Instinct portability — the human side of continuous learning.

Export your learned instincts to a JSON file for sharing, or import others' instincts into
your memory. Imported instincts are tagged with their origin and never overwrite a local
instinct with higher confidence. Stdlib only.

Usage:
  python scripts/instincts.py export <out.json> [db]
  python scripts/instincts.py import <in.json>  [db]
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_DB = ".claude/hooks/memory/pqa_memory.db"


def _conn(db: str) -> sqlite3.Connection:
    return sqlite3.connect(db)


def export(db: str, out: str) -> int:
    conn = _conn(db)
    rows = conn.execute(
        "SELECT name, statement, confidence, evidence_n, origin"
        " FROM instincts ORDER BY confidence DESC"
    ).fetchall()
    conn.close()
    payload = {
        "format": "pqa-instincts/1",
        "exported_at": int(time.time()),
        "instincts": [
            dict(zip(("name", "statement", "confidence", "evidence_n", "origin"), r, strict=True))
            for r in rows
        ],
    }
    Path(out).write_text(json.dumps(payload, indent=2))
    print(f"exported {len(rows)} instincts -> {out}")
    return 0


def import_(db: str, src: str) -> int:
    data = json.loads(Path(src).read_text())
    if data.get("format") != "pqa-instincts/1":
        print("unrecognised instinct file format", file=sys.stderr)
        return 1
    conn = _conn(db)
    tag = f"import:{Path(src).stem}"
    added = 0
    for it in data.get("instincts", []):
        existing = conn.execute(
            "SELECT confidence FROM instincts WHERE name=?", (it["name"],)
        ).fetchone()
        if existing and existing[0] >= it.get("confidence", 0):
            continue  # never overwrite a better local instinct
        conn.execute(
            "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
            "statement=excluded.statement, confidence=excluded.confidence, origin=excluded.origin",
            (
                it["name"],
                it["statement"],
                float(it.get("confidence", 0.5)),
                int(it.get("evidence_n", 0)),
                tag,
                int(time.time()),
            ),
        )
        added += 1
    conn.commit()
    conn.close()
    print(f"imported/updated {added} instincts from {src} (tagged {tag})")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd, path = argv[1], argv[2]
    db = argv[3] if len(argv) > 3 else DEFAULT_DB
    if cmd == "export":
        return export(db, path)
    if cmd == "import":
        return import_(db, path)
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
