"""Cost-governor: per-run budget cap with a hard abort and live spend tracking.

Each generator/adversary/verifier call records `(branch, model, input_tokens, output_tokens)`.
The governor computes cost from a model price table, sums across branches, and refuses to
proceed past the cap. Status moves ok → warn → abort as the run climbs the budget; abort is
absolute. Thread-safe so parallel branches (worktree mode) can record concurrently.

Why a cost cap matters: with N branches x subagents on Opus, a runaway loop can rack up real
money fast. Phase 0 / 1 cannot ship without it — flagged Gap #6 in the plan.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

Status = Literal["ok", "warn", "abort"]

# Per-million-token pricing (USD), standard tier. Keep current with vendor pricing.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
}


@dataclass(frozen=True)
class Budget:
    max_usd: float
    warn_at: float = 0.8

    def __post_init__(self) -> None:
        if self.max_usd <= 0:
            raise ValueError(f"max_usd must be positive, got {self.max_usd}")
        if not 0 < self.warn_at < 1:
            raise ValueError(f"warn_at must be in (0, 1), got {self.warn_at}")


@dataclass(frozen=True)
class Spend:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def cost_for(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD for one model call. Raises KeyError on unknown models — a typo here is
    a real bug, not something to silently default."""
    in_per_mil, out_per_mil = MODEL_PRICING[model]
    return (input_tokens * in_per_mil + output_tokens * out_per_mil) / 1_000_000


class CostGovernor:
    """Tracks spend per branch and decides ok/warn/abort against a Budget."""

    def __init__(self, budget: Budget) -> None:
        self._budget = budget
        self._per_branch: dict[str, Spend] = {}
        self._lock = threading.Lock()

    def record(self, branch_id: str, model: str, input_tokens: int, output_tokens: int) -> None:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError(
                "token counts must be non-negative, "
                f"got input={input_tokens} output={output_tokens}"
            )
        cost = cost_for(model, input_tokens, output_tokens)
        with self._lock:
            prev = self._per_branch.get(branch_id, Spend())
            self._per_branch[branch_id] = Spend(
                input_tokens=prev.input_tokens + input_tokens,
                output_tokens=prev.output_tokens + output_tokens,
                cost_usd=prev.cost_usd + cost,
            )

    def per_branch(self) -> dict[str, Spend]:
        with self._lock:
            return dict(self._per_branch)

    def total(self) -> Spend:
        with self._lock:
            spends = list(self._per_branch.values())
        return Spend(
            input_tokens=sum(s.input_tokens for s in spends),
            output_tokens=sum(s.output_tokens for s in spends),
            cost_usd=sum(s.cost_usd for s in spends),
        )

    def status(self) -> Status:
        spent = self.total().cost_usd
        if spent >= self._budget.max_usd:
            return "abort"
        if spent >= self._budget.max_usd * self._budget.warn_at:
            return "warn"
        return "ok"

    def should_abort(self) -> bool:
        return self.status() == "abort"

    def remaining_usd(self) -> float:
        return max(0.0, self._budget.max_usd - self.total().cost_usd)

    def report(self) -> str:
        total = self.total()
        lines = [
            f"status: {self.status()}",
            f"spent: ${total.cost_usd:.4f} of ${self._budget.max_usd:.2f}",
            f"remaining: ${self.remaining_usd():.4f}",
            f"tokens: in={total.input_tokens:,}, out={total.output_tokens:,}",
            "branches:",
        ]
        for branch_id, spend in sorted(self.per_branch().items()):
            lines.append(
                f"  {branch_id}: ${spend.cost_usd:.4f} "
                f"({spend.input_tokens:,} in, {spend.output_tokens:,} out)"
            )
        return "\n".join(lines)
