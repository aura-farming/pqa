"""Superposition: spawn N branches with different topologies.

Phase 0 — in-context branches. The orchestrator holds the Branch list, the generator
writes into each branch's .output, and validate_divergence checks the populated outputs
against pqa.divergence. No worktrees yet.

Phase 2 will swap the in-context implementation for git worktrees behind the same
Branch / spawn / validate interface, so the orchestrator code does not change when we
move from "branches share the working tree" to "branches each get their own worktree".

The plan calls this "spawning" but actual generation happens elsewhere (subagent or
direct model call) — this module produces the divergent prompts that go INTO generation
and the validation pass that runs ON the outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pqa.divergence import DivergenceReport, measure_divergence
from pqa.frame import Disagreement


@dataclass(frozen=True)
class Branch:
    """One branch in a superposition. Phase 0: the .output is filled in-context by the
    generator; Phase 2: .output reflects what the worktree's generator wrote to disk."""

    id: str
    prompt: str
    output: str = ""
    conviction: str | None = None  # high/medium/low/None — telemetry only
    incremental: bool = True  # False = quantum-jump branch
    model: str = "claude-sonnet-4-6"


@dataclass(frozen=True)
class RespawnPlan:
    """The orchestrator's next move after divergence validation."""

    action: Literal["proceed", "respawn-pair", "abort"]
    pair_indices: tuple[int, int] | None  # for respawn-pair, which two to redo
    reason: str


# Topology axes the prompts cycle through to push branches into different shapes.
# Each axis forces the generator toward a structurally distinct solution, not just a
# differently-named one. The cost-governor will catch wasted runs when this fails.
_AXES = (
    "different data model (change the state shape)",
    "different control flow (sync vs async; push vs pull)",
    "different boundary (where the layer split sits)",
    "different storage assumption",
    "different concurrency assumption",
)


def _topology_for(i: int) -> str:
    return _AXES[i % len(_AXES)]


def spawn_prompts(
    n: int,
    base_prompt: str,
    disagreement: Disagreement | None = None,
    force_non_obvious: int | None = None,
) -> list[str]:
    """Produce N prompt variants. Each carries explicit topology guidance so the
    generator does NOT default to a single style with different identifiers (the
    failure mode pqa.divergence exists to catch).

    `disagreement`, when set, is embedded in the prompts and split — odd-indexed branches
    take the self-eval side, even-indexed branches take the research side — so the
    spawned branches realise the frame collision rather than just hearing about it.

    `force_non_obvious`, when set to an index in [0, n), inserts an explicit P_reframe
    instruction in that branch's prompt so at least one branch genuinely takes the
    low-probability fork.
    """
    if n < 2:
        raise ValueError(f"superposition needs at least 2 branches, got {n}")

    prompts: list[str] = []
    for i in range(n):
        parts = [f"Topology axis #{i}: {_topology_for(i)}."]
        if disagreement is not None:
            side = "self-eval" if i % 2 else "research"
            parts.append(f"Frame disagreement: {disagreement.summary}. Take the {side} side.")
        if i == force_non_obvious:
            parts.append(
                "P_reframe: take the explicitly NON-OBVIOUS fork. "
                "If the obvious answer is X, your job is the best non-X."
            )
        guidance = " ".join(parts)
        prompts.append(f"{guidance}\n\n{base_prompt}")
    return prompts


def validate_divergence(
    branches: list[Branch],
    collapsed_at: float = 0.95,
    divergent_below: float = 0.7,
) -> DivergenceReport:
    """Run the divergence check on N populated branches (each `.output` set)."""
    return measure_divergence(
        [b.output for b in branches],
        collapsed_at=collapsed_at,
        divergent_below=divergent_below,
    )


def respawn_plan(report: DivergenceReport) -> RespawnPlan:
    """Translate a DivergenceReport into the orchestrator's next move:
    proceed → run collision; respawn-pair → redo the most similar branch only;
    abort → throw the whole superposition out and re-spawn from scratch."""
    if report.verdict == "divergent":
        return RespawnPlan(
            action="proceed",
            pair_indices=None,
            reason="branches are topologically distinct",
        )
    if report.verdict == "low-variance":
        return RespawnPlan(
            action="respawn-pair",
            pair_indices=report.most_similar_pair,
            reason="one pair too similar; re-spawn the most similar branch",
        )
    return RespawnPlan(
        action="abort",
        pair_indices=None,
        reason="superposition collapsed; abort and re-spawn from scratch",
    )
