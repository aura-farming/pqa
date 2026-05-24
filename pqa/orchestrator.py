"""PQA orchestrator — the main loop.

Ties every Phase-0 module together into one runnable pass:

    frame collision -> spawn topology-diverse prompts -> generate (delegated) ->
    divergence validation -> adversary attack -> verifier -> collapse pick survivor ->
    persist precipitate + failures -> update frame.resolved_by -> baseline compare ->
    emit RunReport.

Cost-governed throughout: every model call records into a CostGovernor, and the loop
aborts cleanly (returning a partial RunReport) the moment the budget cap is crossed.
Phase 0 runs branches sequentially in-context (no worktrees). Phase 2 will swap that
for parallel worktree spawning behind the same Branch interface — this function does
not change when that happens.

Generators, adversaries, and verifiers are external callables (subagent / model / mock)
because the orchestrator itself must stay deterministic and testable. Each callable
returns the artefact PLUS the token counts it spent, so the cost-governor can record
real spend without observing model calls directly.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass

from pqa.baseline import Baseline, Comparison, compare
from pqa.collapse import BranchResult, CollapseOutcome, select_survivor
from pqa.collision import Finding, score_all
from pqa.cost import Budget, CostGovernor
from pqa.divergence import DivergenceReport
from pqa.frame import Frame, detect_disagreement, record_frame, update_resolved_by
from pqa.memory import Failure, record_failure, record_precipitate
from pqa.superposition import Branch, respawn_plan, spawn_prompts, validate_divergence


@dataclass(frozen=True)
class VerifyResult:
    """The verifier's per-branch output."""

    has_tests: bool
    verified: bool
    coverage: float | None


# Callable types — kept as plain Callable aliases rather than Protocol classes so that
# fakes in tests don't need to subclass anything.
GeneratorFn = Callable[[Branch], tuple[Branch, int, int]]  # -> populated branch, in/out tokens
AdversaryFn = Callable[[list[Branch]], tuple[list[Finding], int, int]]
VerifierFn = Callable[[Branch], VerifyResult]


@dataclass(frozen=True)
class RunReport:
    task: str
    session_id: str
    survivor: Branch | None
    survivor_result: BranchResult | None
    collapse: CollapseOutcome
    divergence: DivergenceReport | None
    cost_report: str
    baseline_comparison: Comparison | None
    branches: list[Branch]
    branch_results: list[BranchResult]
    aborted: bool
    abort_reason: str | None
    started_at: int
    finished_at: int


# Default model used to price generator/adversary/verifier calls. The fake test callables
# don't care — they pass token counts directly. Real callables can override per-call when
# the orchestrator wraps them.
_DEFAULT_MODEL = "claude-sonnet-4-6"


def _aborted_report(
    task: str,
    session_id: str,
    reason: str,
    branches: list[Branch],
    branch_results: list[BranchResult],
    divergence: DivergenceReport | None,
    governor: CostGovernor,
    started_at: int,
) -> RunReport:
    return RunReport(
        task=task,
        session_id=session_id,
        survivor=None,
        survivor_result=None,
        collapse=CollapseOutcome(None, reason, False, "aborted"),
        divergence=divergence,
        cost_report=governor.report(),
        baseline_comparison=None,
        branches=branches,
        branch_results=branch_results,
        aborted=True,
        abort_reason=reason,
        started_at=started_at,
        finished_at=int(time.time()),
    )


def _generate_all(
    n: int,
    base_prompt: str,
    research: Frame,
    selfeval: Frame,
    generator: GeneratorFn,
    governor: CostGovernor,
    force_non_obvious: int | None,
) -> tuple[list[Branch], str | None]:
    """Spawn N prompts and generate each branch sequentially. Returns the branches plus
    an abort reason string if the cost cap tripped mid-generation."""
    disagreement = detect_disagreement(research, selfeval)
    prompts = spawn_prompts(
        n,
        base_prompt,
        disagreement=disagreement,
        force_non_obvious=force_non_obvious,
    )
    branches: list[Branch] = []
    for i, prompt in enumerate(prompts):
        seed = Branch(id=f"b{i}", prompt=prompt, incremental=(i != force_non_obvious))
        populated, in_tok, out_tok = generator(seed)
        governor.record(populated.id, populated.model, in_tok, out_tok)
        branches.append(populated)
        if governor.should_abort():
            return branches, "cost budget exceeded during generation"
    return branches, None


def _resolved_view(survivor: Branch, branches: list[Branch]) -> str:
    """For the frame.resolved_by column: which side of the disagreement did the survivor
    align with? Phase 0 uses parity (even-indexed = research; odd-indexed = self-eval),
    matching the spawn_prompts split."""
    index = next((i for i, b in enumerate(branches) if b.id == survivor.id), 0)
    return "research" if index % 2 == 0 else "selfeval"


def run(
    task: str,
    session_id: str,
    base_prompt: str,
    research: Frame,
    selfeval: Frame,
    generator: GeneratorFn,
    adversary: AdversaryFn,
    verifier: VerifierFn,
    budget: Budget,
    conn: sqlite3.Connection,
    n_branches: int = 2,
    baseline: Baseline | None = None,
    force_non_obvious: int | None = None,
) -> RunReport:
    """One PQA run, end-to-end.

    Returns a RunReport regardless of outcome — even an aborted run produces a report
    with `aborted=True` and the cost-governor snapshot, so the caller can persist it
    and learn from it.
    """
    started_at = int(time.time())
    governor = CostGovernor(budget)

    # ---- 1. Frame collision ------------------------------------------------
    disagreement = detect_disagreement(research, selfeval)
    frame_id = record_frame(conn, session_id, task, research, selfeval, disagreement)

    # ---- 2. Spawn + generate ----------------------------------------------
    branches, abort = _generate_all(
        n_branches, base_prompt, research, selfeval, generator, governor, force_non_obvious
    )
    if abort:
        return _aborted_report(task, session_id, abort, branches, [], None, governor, started_at)

    # ---- 3. Divergence gate ------------------------------------------------
    divergence = validate_divergence(branches)
    plan = respawn_plan(divergence)
    if plan.action == "abort":
        return _aborted_report(
            task,
            session_id,
            f"superposition collapsed ({plan.reason})",
            branches,
            [],
            divergence,
            governor,
            started_at,
        )

    # ---- 4. Adversary ------------------------------------------------------
    findings, adv_in, adv_out = adversary(branches)
    governor.record("adversary", _DEFAULT_MODEL, adv_in, adv_out)
    if governor.should_abort():
        return _aborted_report(
            task,
            session_id,
            "cost budget exceeded after adversary attack",
            branches,
            [],
            divergence,
            governor,
            started_at,
        )
    scores = score_all(findings, branch_ids=[b.id for b in branches])

    # ---- 5. Verifier per branch -------------------------------------------
    verify_results: dict[str, VerifyResult] = {}
    for b in branches:
        verify_results[b.id] = verifier(b)
        # Verifier work is mostly compute (tests), not model tokens, so we don't charge
        # cost-governor for it here. When real verifier subagent runs (Phase 1), it'll
        # report its own tokens — add the .record() call there.

    # ---- 6. Build BranchResults -------------------------------------------
    branch_results: list[BranchResult] = []
    for b in branches:
        score = scores[b.id]
        vr = verify_results[b.id]
        # A critical unresolved finding zeroes findings_resolved so collapse drops the
        # branch; the rank-key is monotone in findings_resolved.
        resolved_count = 0 if not score.survives else score.resolved
        branch_results.append(
            BranchResult(
                name=b.id,
                verified=vr.verified and score.survives,
                has_tests=vr.has_tests,
                coverage=vr.coverage,
                findings_resolved=resolved_count,
                findings_total=score.total,
                conviction=b.conviction,
                incremental=b.incremental,
            )
        )

    # ---- 7. Collapse -------------------------------------------------------
    outcome = select_survivor(branch_results)

    # ---- 8. Persist precipitate + failures + resolved_by ------------------
    survivor_branch: Branch | None = None
    baseline_comparison: Comparison | None = None
    if outcome.survivor is not None:
        survivor_branch = next(b for b in branches if b.id == outcome.survivor.name)
        record_precipitate(conn, session_id, task, survivor_branch.id, outcome.reason)
        update_resolved_by(conn, frame_id, _resolved_view(survivor_branch, branches))
        for br in branch_results:
            if br.name != outcome.survivor.name:
                record_failure(
                    conn,
                    session_id,
                    task,
                    Failure(
                        approach=br.name,
                        death_reason=_death_reason(br, findings),
                        conviction=br.conviction or "none",
                    ),
                )
        if baseline is not None:
            total = governor.total()
            baseline_comparison = compare(
                baseline=baseline,
                pqa_response=survivor_branch.output,
                pqa_tokens_used=total.input_tokens + total.output_tokens,
                pqa_tests_pass=outcome.survivor.verified,
                pqa_coverage=outcome.survivor.coverage,
            )
    else:
        # All branches failed verification. Persist every one as a failure so the
        # taxonomy captures the dead-end frame.
        for br in branch_results:
            record_failure(
                conn,
                session_id,
                task,
                Failure(
                    approach=br.name,
                    death_reason=_death_reason(br, findings),
                    conviction=br.conviction or "none",
                ),
            )

    finished_at = int(time.time())
    return RunReport(
        task=task,
        session_id=session_id,
        survivor=survivor_branch,
        survivor_result=outcome.survivor,
        collapse=outcome,
        divergence=divergence,
        cost_report=governor.report(),
        baseline_comparison=baseline_comparison,
        branches=branches,
        branch_results=branch_results,
        aborted=False,
        abort_reason=None,
        started_at=started_at,
        finished_at=finished_at,
    )


def _death_reason(br: BranchResult, findings: list[Finding]) -> str:
    """Compose a one-line cause-of-death for the failure taxonomy."""
    crit = [
        f
        for f in findings
        if f.branch_id == br.name and f.severity == "critical" and not f.resolved
    ]
    if crit:
        titles = ", ".join(f.title for f in crit[:3])
        return f"critical unresolved finding(s): {titles}"
    if not br.verified:
        return "failed verification"
    return "outranked by survivor"
