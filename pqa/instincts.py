"""Instinct synthesis and conviction calibration — the harness's self-knowledge.

Roadmap §7: the moat is ornamental until the loops produce data. This module is the
engine side ("engine code, not agent vibes"): deterministic clustering of precipitates
into instincts with support-derived confidence that decays when failures contradict
it, and the conviction-calibration table that answers "do hunches mean anything here?"

Clustering is overlap-coefficient over word tokens (stdlib-only, rename-cheap) with a
domain affinity rule: precipitates with different explicit domains never cluster, and
a shared domain lowers the similarity bar. Confidence = support / (support + 2),
decayed 0.7x per contradicting failure — `budget:` deaths never contradict (an aborted
run is not evidence; see the failure-taxonomy skill).
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass

# Same token shape as pqa.memory's query tokenizer; duplicated deliberately so this
# module's clustering thresholds stay self-contained and auditable side by side.
_TOKEN = re.compile(r"[A-Za-z0-9_]+")

_CLUSTER_OVERLAP = 0.5  # overlap coefficient required to join a cluster
_SAME_DOMAIN_OVERLAP = 0.35  # lower bar when both rows carry the same domain tag
_CONTRADICTION_OVERLAP = 0.3  # failure-vs-cluster overlap that counts as contradiction
_CONFIDENCE_DECAY = 0.7  # multiplier per contradicting failure
_AGREE_MIN_TOKENS = 2  # statement tokens that must appear in the survivor
_AGREE_TOKEN_LEN = 4  # ignore tiny glue words when judging agreement


@dataclass(frozen=True)
class Instinct:
    name: str
    statement: str
    confidence: float
    evidence_n: int


@dataclass(frozen=True)
class CalibrationRow:
    """One line of the conviction-calibration table. `level` is high/medium/low or
    'base' (the all-branches win rate the levels are read against). `n` counts signals
    WITH outcomes; `pending` counts signals still awaiting back-fill — pending > 0 on
    a finished run means the back-fill loop is broken, not that hunches are unclear."""

    level: str
    n: int
    wins: int
    p_win: float
    pending: int


@dataclass(frozen=True)
class _Row:
    id: int
    name: str
    rationale: str
    domain: str | None
    tokens: frozenset[str]


def _tokens(text: str, min_len: int = 2) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall(text.lower()) if len(t) >= min_len)


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    """Overlap coefficient — |a∩b| / min(|a|,|b|). More robust than Jaccard on short
    texts, where one verbose row would otherwise dilute a genuine match."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _cluster_rows(rows: list[_Row]) -> list[list[_Row]]:
    """Greedy and deterministic: each row joins the first cluster whose representative
    (earliest member) is similar enough, else starts its own. Different explicit
    domains never cluster; a shared domain lowers the bar."""
    clusters: list[list[_Row]] = []
    for row in rows:
        for cluster in clusters:
            rep = cluster[0]
            if row.domain and rep.domain and row.domain != rep.domain:
                continue
            same_domain = bool(row.domain) and row.domain == rep.domain
            bar = _SAME_DOMAIN_OVERLAP if same_domain else _CLUSTER_OVERLAP
            if _overlap(row.tokens, rep.tokens) >= bar:
                cluster.append(row)
                break
        else:
            clusters.append([row])
    return clusters


def _contradictions(conn: sqlite3.Connection, cluster_tokens: frozenset[str]) -> int:
    """Failures whose text overlaps the cluster — excluding `budget:` deaths, which
    are aborted-not-refuted by taxonomy rule and must never count as evidence."""
    count = 0
    for approach, death in conn.execute("SELECT approach, death_reason FROM failures"):
        if str(death).startswith("budget:"):
            continue
        if _overlap(_tokens(f"{approach} {death}"), cluster_tokens) >= _CONTRADICTION_OVERLAP:
            count += 1
    return count


def _upsert_local(conn: sqlite3.Connection, inst: Instinct) -> None:
    """Insert or refresh a synthesized instinct. Imported instincts are never
    clobbered: the update only applies to rows whose origin is 'local'."""
    conn.execute(
        "INSERT INTO instincts(name, statement, confidence, evidence_n, origin, created_at) "
        "VALUES(?,?,?,?,'local',?) "
        "ON CONFLICT(name) DO UPDATE SET statement=excluded.statement, "
        "confidence=excluded.confidence, evidence_n=excluded.evidence_n "
        "WHERE instincts.origin = 'local'",
        (inst.name, inst.statement, inst.confidence, inst.evidence_n, int(time.time())),
    )


def synthesize_instincts(conn: sqlite3.Connection, *, min_support: int = 2) -> list[Instinct]:
    """Cluster precipitates into instincts and upsert them (origin='local').

    confidence = support / (support + 2), decayed per contradicting failure. The
    earliest precipitate in a cluster names the instinct (stable across re-runs);
    its rationale is the statement. Returns the instincts that met min_support."""
    rows = [
        _Row(r[0], r[1], r[2], r[3], _tokens(f"{r[1]} {r[2]}"))
        for r in conn.execute("SELECT id, name, rationale, domain FROM precipitates ORDER BY id")
    ]
    out: list[Instinct] = []
    for cluster in _cluster_rows(rows):
        if len(cluster) < min_support:
            continue
        union = frozenset(t for r in cluster for t in r.tokens)
        support = len(cluster)
        decay = _CONFIDENCE_DECAY ** _contradictions(conn, union)
        confidence = round(support / (support + 2) * decay, 3)
        inst = Instinct(cluster[0].name, cluster[0].rationale, confidence, support)
        _upsert_local(conn, inst)
        out.append(inst)
    conn.commit()
    return out


def calibration(conn: sqlite3.Connection) -> list[CalibrationRow]:
    """The conviction-calibration table: P(win | level) for every flagged level that
    has signals, plus the 'base' all-branches win rate (precipitates over precipitates
    + non-budget failures) the levels are compared against."""
    rows: list[CalibrationRow] = []
    for level in ("high", "medium", "low"):
        n, wins, pending = conn.execute(
            "SELECT count(CASE WHEN outcome_at IS NOT NULL THEN 1 END), "
            "sum(CASE WHEN outcome_at IS NOT NULL AND won = 1 THEN 1 ELSE 0 END), "
            "count(CASE WHEN outcome_at IS NULL THEN 1 END) "
            "FROM signals WHERE level = ?",
            (level,),
        ).fetchone()
        if n or pending:
            p_win = round((wins or 0) / n, 3) if n else 0.0
            rows.append(CalibrationRow(level, n, wins or 0, p_win, pending))
    precip = conn.execute("SELECT count(*) FROM precipitates").fetchone()[0]
    merit_deaths = conn.execute(
        "SELECT count(*) FROM failures WHERE death_reason NOT LIKE 'budget:%'"
    ).fetchone()[0]
    total = precip + merit_deaths
    base_rate = round(precip / total, 3) if total else 0.0
    rows.append(CalibrationRow("base", total, precip, base_rate, 0))
    return rows


def agrees(statement: str, output: str) -> bool:
    """Heuristic v1 of "the winner agreed with the instinct": at least two substantive
    statement tokens appear in the survivor's output. Deterministic and cheap; the
    eval harness (roadmap §8) is where this gets pressure-tested and refined."""
    statement_tokens = _tokens(statement, min_len=_AGREE_TOKEN_LEN)
    output_tokens = _tokens(output, min_len=_AGREE_TOKEN_LEN)
    return len(statement_tokens & output_tokens) >= _AGREE_MIN_TOKENS
