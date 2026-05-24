#!/usr/bin/env python3
"""Runnable Phase-0 demo: drives the PQA orchestrator end-to-end with synthetic
generator/adversary/verifier callables so the full loop can be exercised without
any subagent or model invocation.

What this proves:
  1. The orchestrator wires every module together (frame → spawn → divergence →
     adversary → verifier → collapse → persist → baseline-compare → RunReport).
  2. The cost-governor records spend across branches and adversary calls.
  3. A critical unresolved finding kills a verified branch (collision evidence
     beats verification on its own).
  4. The frames table's `resolved_by` column is populated after collapse.
  5. The baseline comparator returns a verdict from the side-by-side.

Run from the repo root:
    uv run python examples/phase0_demo.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from textwrap import indent

# PQA is a non-package project (see [tool.uv] package = false in pyproject.toml).
# Tests pick up the import path via pytest's pythonpath setting; standalone scripts
# need to add the repo root explicitly so `from pqa import ...` resolves.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pqa.baseline import record_baseline  # noqa: E402
from pqa.collision import Finding  # noqa: E402
from pqa.cost import Budget  # noqa: E402
from pqa.frame import Frame  # noqa: E402
from pqa.memory import connect  # noqa: E402
from pqa.orchestrator import VerifyResult, run  # noqa: E402
from pqa.report import write_report  # noqa: E402
from pqa.superposition import Branch  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic subagents


def fake_generator(branch: Branch) -> tuple[Branch, int, int]:
    """Pretend to call a model. Two branches, two genuinely-different topologies."""
    outputs = {
        "b0": (
            "def rate_limit(tokens_per_second: float) -> Callable:\n"
            "    bucket = tokens_per_second\n"
            "    last = time.monotonic()\n"
            "    def allow() -> bool:\n"
            "        nonlocal bucket, last\n"
            "        now = time.monotonic()\n"
            "        bucket = min(tokens_per_second, bucket + (now - last) * tokens_per_second)\n"
            "        last = now\n"
            "        if bucket >= 1:\n"
            "            bucket -= 1\n"
            "            return True\n"
            "        return False\n"
            "    return allow\n"
        ),
        "b1": (
            "import asyncio\n"
            "class LeakyBucket:\n"
            "    def __init__(self, capacity: int, leak_per_sec: float):\n"
            "        self.capacity = capacity\n"
            "        self.queue: asyncio.Queue = asyncio.Queue(maxsize=capacity)\n"
            "        self.leak_per_sec = leak_per_sec\n"
            "        self._task: asyncio.Task | None = None\n"
            "    async def submit(self, item) -> bool:\n"
            "        try:\n"
            "            self.queue.put_nowait(item)\n"
            "            return True\n"
            "        except asyncio.QueueFull:\n"
            "            return False\n"
            "    async def run(self) -> None:\n"
            "        while True:\n"
            "            item = await self.queue.get()\n"
            "            yield item\n"
            "            await asyncio.sleep(1 / self.leak_per_sec)\n"
        ),
    }
    out = outputs.get(branch.id, f"# fallback output for {branch.id}\npass\n")
    populated = Branch(
        id=branch.id,
        prompt=branch.prompt,
        output=out,
        conviction="high" if branch.id == "b1" else None,
        incremental=branch.incremental,
        model=branch.model,
    )
    # Pretend each branch cost ~6k input + 2k output tokens.
    return populated, 6_000, 2_000


def fake_adversary(branches: list[Branch]) -> tuple[list[Finding], int, int]:
    """Adversary finds a real issue on b0 but the branch handles it; finds a
    medium-severity issue on b1 it cannot address."""
    findings = [
        Finding(
            branch_id="b0",
            severity="high",
            category="correctness",
            title="bucket can go negative under bursty load",
            detail="under contention `bucket -= 1` can race; needs a lock",
            resolved=True,  # b0 acknowledges via an atomic counter
        ),
        Finding(
            branch_id="b1",
            severity="medium",
            category="complexity",
            title="async iterator state is hard to reset",
            detail="run() loops forever; teardown story is missing",
            resolved=False,
        ),
    ]
    return findings, 3_000, 1_500


def fake_verifier(branch: Branch) -> VerifyResult:
    """Both branches have tests; b0 passes with high coverage, b1 also passes
    but with lower coverage. Without the critical-finding rule this would be a
    toss-up; with collision, b0 wins because its high-severity finding was
    resolved and b1's medium finding wasn't."""
    return {
        "b0": VerifyResult(has_tests=True, verified=True, coverage=92.0),
        "b1": VerifyResult(has_tests=True, verified=True, coverage=74.0),
    }.get(branch.id, VerifyResult(has_tests=False, verified=False, coverage=None))


# ---------------------------------------------------------------------------
# Demo


def main() -> int:
    print("=" * 78)
    print("PQA Phase-0 Demo  —  end-to-end loop with synthetic subagents")
    print("=" * 78)

    research = Frame(
        type="research",
        content=(
            "Token-bucket is the canonical rate limiter. Cited in dozens of references "
            "as the right default for HTTP API throttling."
        ),
        source="docs/rate-limiting/best-practices",
    )
    selfeval = Frame(
        type="selfeval",
        content=(
            "In THIS service the inbound traffic is bursty and the downstream wants "
            "FIFO ordering with backpressure. A leaky-bucket / queue with explicit "
            "backpressure fits better than a token-bucket here."
        ),
        source="self-eval",
    )

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pqa_memory.db"
        conn = connect(db)

        # Pre-record a baseline so the comparator has something to compare against.
        baseline = record_baseline(
            conn,
            task="rate-limiter",
            response="def rate(): return True  # always allow — single-pass stub",
            tokens_used=900,
            tests_pass=False,
            coverage=None,
        )

        report = run(
            task="rate-limiter",
            session_id="demo-1",
            base_prompt="Build a rate limiter for a bursty FIFO inbound queue.",
            research=research,
            selfeval=selfeval,
            generator=fake_generator,
            adversary=fake_adversary,
            verifier=fake_verifier,
            budget=Budget(max_usd=2.0),
            conn=conn,
            n_branches=2,
            baseline=baseline,
        )

        _print_report(report)
        _print_persistence(conn)

        # Persist the run artefact next to the temp DB so the operator can study it
        # after the demo exits. Writes report.json + report.md + branches/*.txt.
        artefact_root = _REPO_ROOT / "artefacts"
        artefact = write_report(report, artefact_root)
        _print_artefact(artefact)

        conn.close()

    print()
    print("Demo complete. Phase 0 loop ran end-to-end without any model call.")
    print("Swap fake_generator/fake_adversary/fake_verifier for real subagent")
    print("invocations and the same orchestrator runs Phase 1 with no changes.")
    return 0


def _print_report(report) -> None:
    print()
    print("RunReport")
    print("-" * 78)
    print(f"  task                : {report.task}")
    print(f"  session_id          : {report.session_id}")
    print(f"  aborted             : {report.aborted}")
    if report.aborted:
        print(f"  abort_reason        : {report.abort_reason}")
    print(f"  branches generated  : {len(report.branches)}")
    if report.divergence is not None:
        print(f"  divergence verdict  : {report.divergence.verdict}")
        print(f"  mean similarity     : {report.divergence.mean_similarity:.3f}")
    print(f"  collapse reason     : {report.collapse.reason}")
    print(f"  confidence          : {report.collapse.confidence}")
    if report.survivor is not None:
        print(f"  survivor            : {report.survivor.id}")
        print(f"  survivor conviction : {report.survivor.conviction}")
    if report.baseline_comparison is not None:
        bc = report.baseline_comparison
        print(f"  baseline verdict    : {bc.verdict}")
        print(f"  baseline rationale  : {bc.rationale}")
        print(f"  baseline tokens     : {bc.baseline.tokens_used}")
        print(f"  pqa tokens          : {bc.pqa_tokens_used}")
    print()
    print("  cost report:")
    print(indent(report.cost_report, "    "))


def _print_artefact(artefact) -> None:
    print()
    print("Artefact written")
    print("-" * 78)
    print(f"  directory : {artefact.artefact_dir}")
    print(f"  json      : {artefact.json_path}")
    print(f"  markdown  : {artefact.markdown_path}")
    print()
    print(f"  Inspect with:  cat {artefact.markdown_path}")


def _print_persistence(conn) -> None:
    print()
    print("Memory snapshot")
    print("-" * 78)

    precipitates = conn.execute("SELECT name, rationale FROM precipitates ORDER BY id").fetchall()
    print(f"  precipitates ({len(precipitates)}):")
    for name, rationale in precipitates:
        print(f"    - {name}: {rationale}")

    failures = conn.execute(
        "SELECT approach, death_reason, conviction FROM failures ORDER BY id"
    ).fetchall()
    print(f"  failures ({len(failures)}):")
    for approach, reason, conviction in failures:
        print(f"    - {approach}: {reason} (conviction={conviction})")

    frames = conn.execute("SELECT disagreement, resolved_by FROM frames ORDER BY id").fetchall()
    print(f"  frames ({len(frames)}):")
    for disagreement, resolved_by in frames:
        print(f"    - disagreement: {disagreement!r}")
        print(f"      resolved_by : {resolved_by}")


if __name__ == "__main__":
    raise SystemExit(main())
