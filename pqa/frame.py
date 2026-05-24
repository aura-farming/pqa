"""Frame loader + disagreement detection.

PQA's first collision is the gap between two frames: research (what current docs/sources
say is correct) and self-eval (what's actually true in this codebase or context). The gap
is the first branching axis — generators spawn from that disagreement rather than from
the prompt alone. Without explicitly capturing both views and naming where they diverge,
the harness drifts toward research-only thinking and stops being self-honest.

This module is the data model for the two frames, the disagreement detector, and the
persistence layer for the `frames` table. The actual frame content comes from subagents
(pqa-researcher for research; a self-eval pass against the codebase for selfeval) — this
module records what they emit, decides whether the gap is real, and lets collapse
back-fill which view the verifier ultimately favoured (`resolved_by`).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

from pqa.divergence import similarity

FrameType = Literal["research", "selfeval"]


@dataclass(frozen=True)
class Frame:
    type: FrameType
    content: str
    source: str  # research: URL/doc/citation; selfeval: "self-eval" or a context tag


@dataclass(frozen=True)
class Disagreement:
    research: Frame
    selfeval: Frame
    similarity: float  # 0..1; low = real gap, high = the frames are saying the same thing
    summary: str


def detect_disagreement(
    research: Frame,
    selfeval: Frame,
    agreement_above: float = 0.85,
) -> Disagreement | None:
    """Return a Disagreement when the two views diverge enough to branch on; None when
    they agree under the threshold. The threshold default of 0.85 is deliberately strict
    — minor wording differences should NOT count as a disagreement, because spawning
    branches on noise wastes the run."""
    if research.type != "research":
        raise ValueError(f"first arg must be type='research', got {research.type!r}")
    if selfeval.type != "selfeval":
        raise ValueError(f"second arg must be type='selfeval', got {selfeval.type!r}")
    sim = similarity(research.content, selfeval.content)
    if sim >= agreement_above:
        return None
    return Disagreement(
        research=research,
        selfeval=selfeval,
        similarity=sim,
        summary=f"research and self-eval diverge (similarity={sim:.2f})",
    )


def record_frame(
    conn: sqlite3.Connection,
    session_id: str,
    task: str,
    research: Frame,
    selfeval: Frame,
    disagreement: Disagreement | None,
) -> int:
    """Persist a frame snapshot to the `frames` table and return the inserted row id.
    A None `disagreement` records SQL NULL — useful so post-hoc analysis can tell apart
    "we never branched because frames agreed" from "we branched and it resolved"."""
    cur = conn.execute(
        "INSERT INTO frames(session_id, task, research_view, selfeval_view, disagreement, "
        "created_at) VALUES(?,?,?,?,?,?)",
        (
            session_id,
            task,
            research.content,
            selfeval.content,
            disagreement.summary if disagreement else None,
            int(time.time()),
        ),
    )
    conn.commit()
    return cur.lastrowid or 0


def update_resolved_by(conn: sqlite3.Connection, frame_id: int, resolved_by: str) -> None:
    """After collapse picks a survivor, record which view (research/selfeval) it
    actually came from. This is the calibration signal the self-reflector uses to
    judge how often each frame is right."""
    conn.execute("UPDATE frames SET resolved_by = ? WHERE id = ?", (resolved_by, frame_id))
    conn.commit()
