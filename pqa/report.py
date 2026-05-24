"""Per-run artefact: a structured report of what one PQA run actually did.

Without a per-run report, the failure taxonomy is just rows in a SQLite table — not
something the operator can show to a stakeholder, study after a divergence, or
reproduce a week later. report.py turns a RunReport into a self-contained on-disk
artefact (JSON + human-readable Markdown + per-branch outputs) and (optionally) a row
in the cost_runs telemetry table. Closes Gap #10 from the plan.

Layout written per run:
    root/
      <session_id>/
        report.json    -- complete structured data
        report.md      -- human-readable side-by-side
        branches/
          b0.txt       -- the full branch output (Phase 1: replaces with worktree path)
          b1.txt
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pqa.cost import CostGovernor
from pqa.orchestrator import RunReport


@dataclass(frozen=True)
class RunArtefact:
    artefact_dir: Path
    json_path: Path
    markdown_path: Path


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclass / Path / non-JSON-native types to JSON-safe shapes.
    Used in place of a custom JSONEncoder because we want stable, predictable output that
    survives nested dataclass refactors without re-tuning the encoder."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result: dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            result[f.name] = _to_jsonable(getattr(obj, f.name))
        return result
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in cast(list[Any], obj)]
    if isinstance(obj, tuple):
        return [_to_jsonable(v) for v in cast(tuple[Any, ...], obj)]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in cast(dict[Any, Any], obj).items()}
    if isinstance(obj, Path):
        return str(obj)
    return obj


def write_report(report: RunReport, root: Path) -> RunArtefact:
    """Materialise a RunReport on disk. The session_id becomes the directory name; the
    output is overwriting (a re-run with the same session_id replaces prior content)
    rather than incrementing, because session_id is supposed to be unique."""
    artefact_dir = Path(root) / report.session_id
    branches_dir = artefact_dir / "branches"
    branches_dir.mkdir(parents=True, exist_ok=True)

    for branch in report.branches:
        (branches_dir / f"{branch.id}.txt").write_text(branch.output)

    json_path = artefact_dir / "report.json"
    json_path.write_text(json.dumps(_to_jsonable(report), indent=2, sort_keys=False))

    markdown_path = artefact_dir / "report.md"
    markdown_path.write_text(_to_markdown(report))

    return RunArtefact(
        artefact_dir=artefact_dir,
        json_path=json_path,
        markdown_path=markdown_path,
    )


def _fmt_ts(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC).isoformat()


def _to_markdown(report: RunReport) -> str:
    lines: list[str] = []
    title_suffix = " (ABORTED)" if report.aborted else ""
    lines.append(f"# PQA Run Report{title_suffix}")
    lines.append("")
    lines.append(f"- **Task:** `{report.task}`")
    lines.append(f"- **Session:** `{report.session_id}`")
    lines.append(f"- **Started:** {_fmt_ts(report.started_at)}")
    lines.append(f"- **Finished:** {_fmt_ts(report.finished_at)}")
    lines.append(f"- **Aborted:** {report.aborted}")
    if report.aborted and report.abort_reason:
        lines.append(f"- **Abort reason:** {report.abort_reason}")
    lines.append("")

    if report.divergence is not None:
        lines.append("## Divergence")
        lines.append(f"- **Verdict:** `{report.divergence.verdict}`")
        lines.append(f"- **Mean similarity:** {report.divergence.mean_similarity:.3f}")
        lines.append(f"- **Max similarity:** {report.divergence.max_similarity:.3f}")
        lines.append(f"- **Min similarity:** {report.divergence.min_similarity:.3f}")
        if report.divergence.most_similar_pair is not None:
            a, b = report.divergence.most_similar_pair
            lines.append(f"- **Most similar pair:** branches[{a}], branches[{b}]")
        lines.append("")

    lines.append("## Branches")
    lines.append("")
    lines.append("| id | conviction | incremental | model |")
    lines.append("| --- | --- | --- | --- |")
    for branch in report.branches:
        lines.append(
            f"| `{branch.id}` "
            f"| {branch.conviction or '—'} "
            f"| {branch.incremental} "
            f"| {branch.model} |"
        )
    lines.append("")

    if report.branch_results:
        lines.append("## Branch results")
        lines.append("")
        lines.append(
            "| name | verified | has_tests | coverage | findings resolved | findings total |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for br in report.branch_results:
            coverage = f"{br.coverage:.0f}%" if br.coverage is not None else "—"
            lines.append(
                f"| `{br.name}` "
                f"| {br.verified} "
                f"| {br.has_tests} "
                f"| {coverage} "
                f"| {br.findings_resolved} "
                f"| {br.findings_total} |"
            )
        lines.append("")

    lines.append("## Collapse")
    lines.append(f"- **Reason:** {report.collapse.reason}")
    lines.append(f"- **Confidence:** {report.collapse.confidence}")
    if report.survivor is not None:
        lines.append(f"- **Survivor:** `{report.survivor.id}`")
    else:
        lines.append("- **Survivor:** none")
    lines.append("")

    if report.baseline_comparison is not None:
        bc = report.baseline_comparison
        lines.append("## Baseline comparison")
        lines.append(f"- **Verdict:** `{bc.verdict}`")
        lines.append(f"- **Rationale:** {bc.rationale}")
        lines.append(f"- **Baseline tokens:** {bc.baseline.tokens_used}")
        lines.append(f"- **PQA tokens:** {bc.pqa_tokens_used}")
        lines.append("")

    lines.append("## Cost")
    lines.append("")
    lines.append("```")
    lines.append(report.cost_report)
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def record_cost_run(
    conn: sqlite3.Connection,
    session_id: str,
    task: str | None,
    governor: CostGovernor,
    budget_usd: float,
) -> int:
    """Persist a snapshot of the cost-governor state at run end to the cost_runs
    telemetry table. The cost-per-converged-task trend is what flags economically
    broken runs over time."""
    total = governor.total()
    branches = len(governor.per_branch())
    cur = conn.execute(
        "INSERT INTO cost_runs(session_id, task, total_cost, budget_usd, status, branches, "
        "created_at) VALUES(?,?,?,?,?,?,?)",
        (
            session_id,
            task,
            total.cost_usd,
            budget_usd,
            governor.status(),
            branches,
            int(time.time()),
        ),
    )
    conn.commit()
    return cur.lastrowid or 0
