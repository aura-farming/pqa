"""Divergence measurement: did superposition actually produce distinct topologies?

The plan asserts "branches must differ in topology, not style" but does not measure it,
so superposition can silently collapse into N near-identical branches and waste the whole
run's spend. This module closes that gap (Gap #8). It compares branches by AST shape —
node types in pre-order traversal — so renaming a variable or reformatting does NOT count
as topological divergence, but changing the operator, control flow, or class structure
does. Non-Python branches fall back to text similarity.

The orchestrator uses the verdict to decide: divergent → proceed; low-variance → re-spawn
the most similar pair; collapsed → abort and re-spawn the entire superposition.
"""

from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["divergent", "low-variance", "collapsed"]


@dataclass(frozen=True)
class BranchSimilarity:
    branch_a: int  # index into the input list
    branch_b: int
    similarity: float  # 0.0 = totally different, 1.0 = identical topology


@dataclass(frozen=True)
class DivergenceReport:
    pair_similarities: list[BranchSimilarity]
    mean_similarity: float
    max_similarity: float
    min_similarity: float
    most_similar_pair: tuple[int, int] | None
    verdict: Verdict


def _shape(text: str) -> str:
    """Pre-order AST node-type fingerprint for topology comparison.

    Two snippets with the same AST shape but different identifiers produce identical
    fingerprints, so "topology not style" actually means something. Non-parseable text
    falls back to its whitespace-stripped form so this still does *something* useful
    for non-Python branches.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "".join(text.split())

    parts: list[str] = []

    def visit(node: ast.AST, depth: int) -> None:
        parts.append(f"{depth}:{type(node).__name__}")
        for child in ast.iter_child_nodes(node):
            visit(child, depth + 1)

    visit(tree, 0)
    return "\n".join(parts)


def similarity(a: str, b: str) -> float:
    """Topology similarity in [0, 1]. 1.0 = identical AST shape (or identical text on
    non-Python). Renaming a variable or reformatting whitespace does not move this score."""
    return difflib.SequenceMatcher(None, _shape(a), _shape(b)).ratio()


def _verdict(mean: float, max_sim: float, collapsed_at: float, divergent_below: float) -> Verdict:
    if mean >= collapsed_at:
        return "collapsed"
    if max_sim >= collapsed_at or mean >= divergent_below:
        return "low-variance"
    return "divergent"


def measure_divergence(
    branches: list[str],
    collapsed_at: float = 0.95,
    divergent_below: float = 0.7,
) -> DivergenceReport:
    """Score every pair of branches and return a verdict the orchestrator can act on.

    A superposition of 0 or 1 branches is treated as "collapsed" — there is no
    superposition to evaluate, and treating it as anything else would let a degenerate
    run sneak past the divergence gate.
    """
    n = len(branches)
    if n < 2:
        return DivergenceReport(
            pair_similarities=[],
            mean_similarity=0.0,
            max_similarity=0.0,
            min_similarity=0.0,
            most_similar_pair=None,
            verdict="collapsed",
        )

    pairs: list[BranchSimilarity] = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append(
                BranchSimilarity(
                    branch_a=i,
                    branch_b=j,
                    similarity=similarity(branches[i], branches[j]),
                )
            )

    sims = [p.similarity for p in pairs]
    mean_sim = sum(sims) / len(sims)
    max_sim = max(sims)
    min_sim = min(sims)
    most_similar = max(pairs, key=lambda p: p.similarity)

    return DivergenceReport(
        pair_similarities=pairs,
        mean_similarity=mean_sim,
        max_similarity=max_sim,
        min_similarity=min_sim,
        most_similar_pair=(most_similar.branch_a, most_similar.branch_b),
        verdict=_verdict(mean_sim, max_sim, collapsed_at, divergent_below),
    )
