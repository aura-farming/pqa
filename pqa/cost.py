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

# Per-million-token pricing (USD), standard tier, from platform.claude.com/docs pricing.
# PRICING_AS_OF pins the date these numbers were verified against the vendor table; the
# test suite asserts the table matches these published rates so drift is caught in CI,
# not in a user's budget gate.
PRICING_AS_OF = "2026-06-10"

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Operator-facing aliases (what `pqa-config.toml` / `PQA_MODEL` accept) -> concrete
# pricing/dispatch keys. This is the single translation point between the config's
# declared preference and everything that prices or dispatches a model call.
MODEL_ALIASES: dict[str, str] = {
    "fable": "claude-fable-5",
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}


def resolve_model(name: str) -> str:
    """Resolve an alias or concrete model id to a MODEL_PRICING key.

    Accepts either an operator alias (``opus``) or a concrete id
    (``claude-opus-4-8``). Raises KeyError on anything else — a typo here is
    a real bug, not something to silently default.
    """
    concrete = MODEL_ALIASES.get(name, name)
    if concrete not in MODEL_PRICING:
        known = sorted(MODEL_ALIASES) + sorted(MODEL_PRICING)
        raise KeyError(f"unknown model {name!r}; known: {', '.join(known)}")
    return concrete


@dataclass(frozen=True)
class Budget:
    """Run budget. ``max_tokens`` is the primary ledger — PQA runs on a Claude Code
    subscription where USD is synthetic but tokens, rate limits, and context are real.
    ``max_usd`` stays as the secondary cap and the display currency for API-mode users.
    Either cap tripping aborts the run."""

    max_usd: float
    warn_at: float = 0.8
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_usd <= 0:
            raise ValueError(f"max_usd must be positive, got {self.max_usd}")
        if not 0 < self.warn_at < 1:
            raise ValueError(f"warn_at must be in (0, 1), got {self.warn_at}")
        if self.max_tokens is not None and (
            isinstance(self.max_tokens, bool) or self.max_tokens <= 0
        ):
            raise ValueError(f"max_tokens must be a positive int or None, got {self.max_tokens!r}")


@dataclass(frozen=True)
class Spend:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def cost_for(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD for one model call. Accepts aliases or concrete ids. Raises KeyError
    on unknown models — a typo here is a real bug, not something to silently default."""
    in_per_mil, out_per_mil = MODEL_PRICING[resolve_model(model)]
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

    def _snapshot_under_lock(self) -> tuple[Spend, dict[str, Spend], Status]:
        """Compute every observable in a single lock acquisition. Eliminates the
        TOCTOU race where another thread can record spend between sequential
        lock acquisitions in `status()` / `total()` / `report()`."""
        with self._lock:
            per_branch_copy = dict(self._per_branch)
            spends = list(self._per_branch.values())
        total = Spend(
            input_tokens=sum(s.input_tokens for s in spends),
            output_tokens=sum(s.output_tokens for s in spends),
            cost_usd=sum(s.cost_usd for s in spends),
        )
        status = self._status_from(total.cost_usd, total.input_tokens + total.output_tokens)
        return total, per_branch_copy, status

    def _status_from(self, spent_usd: float, spent_tokens: int) -> Status:
        """Pure function: classify known spend against the budget on BOTH axes.
        Tokens are the primary ledger (subscription runs have no marginal USD cost);
        USD remains the secondary cap. Either axis tripping aborts. No lock needed
        because the inputs are already a snapshot."""
        max_tok = self._budget.max_tokens
        if spent_usd >= self._budget.max_usd:
            return "abort"
        if max_tok is not None and spent_tokens >= max_tok:
            return "abort"
        if spent_usd >= self._budget.max_usd * self._budget.warn_at:
            return "warn"
        if max_tok is not None and spent_tokens >= max_tok * self._budget.warn_at:
            return "warn"
        return "ok"

    def total(self) -> Spend:
        total, _per_branch, _status = self._snapshot_under_lock()
        return total

    def status(self) -> Status:
        _total, _per_branch, status = self._snapshot_under_lock()
        return status

    def should_abort(self) -> bool:
        """Single atomic check used in the hot abort path. Acquires the lock
        once — no gap between reading the total and gating on it."""
        _total, _per_branch, status = self._snapshot_under_lock()
        return status == "abort"

    def would_abort(
        self,
        model: str,
        projected_input_tokens: int,
        projected_output_tokens: int,
    ) -> bool:
        """Pre-flight gate: True if recording the projected dispatch would push total
        spend past the cap. Use BEFORE dispatching expensive operations whose spend is
        only recorded after the call returns (e.g. Task tool dispatches). Pure projection
        — does not mutate state. Single lock acquisition, no TOCTOU between projection
        and gate decision. Closes issue #32: should_abort() can only catch overspend
        after the fact; would_abort() catches it before."""
        if projected_input_tokens < 0 or projected_output_tokens < 0:
            raise ValueError(
                "projected token counts must be non-negative, "
                f"got input={projected_input_tokens} output={projected_output_tokens}"
            )
        projected_cost = cost_for(model, projected_input_tokens, projected_output_tokens)
        total, _per_branch, _status = self._snapshot_under_lock()
        projected_tokens = (
            total.input_tokens
            + total.output_tokens
            + projected_input_tokens
            + projected_output_tokens
        )
        return self._status_from(total.cost_usd + projected_cost, projected_tokens) == "abort"

    def remaining_usd(self) -> float:
        total, _per_branch, _status = self._snapshot_under_lock()
        return max(0.0, self._budget.max_usd - total.cost_usd)

    def remaining_tokens(self) -> int | None:
        """Tokens left under the token cap, or None when no token cap is set."""
        if self._budget.max_tokens is None:
            return None
        total, _per_branch, _status = self._snapshot_under_lock()
        return max(0, self._budget.max_tokens - total.input_tokens - total.output_tokens)

    def report(self) -> str:
        """Single-snapshot report so the displayed status, total, remaining, and
        per-branch breakdown are all consistent with each other. Previously the
        report could show status=ok while the snapshot already reflected abort,
        because each component was queried under a separate lock acquisition."""
        total, per_branch_copy, status = self._snapshot_under_lock()
        remaining = max(0.0, self._budget.max_usd - total.cost_usd)
        lines = [
            f"status: {status}",
            f"spent: ${total.cost_usd:.4f} of ${self._budget.max_usd:.2f}",
            f"remaining: ${remaining:.4f}",
            f"tokens: in={total.input_tokens:,}, out={total.output_tokens:,}",
        ]
        if self._budget.max_tokens is not None:
            used = total.input_tokens + total.output_tokens
            lines.append(f"token budget: {used:,} of {self._budget.max_tokens:,}")
        lines.append("branches:")
        for branch_id, spend in sorted(per_branch_copy.items()):
            lines.append(
                f"  {branch_id}: ${spend.cost_usd:.4f} "
                f"({spend.input_tokens:,} in, {spend.output_tokens:,} out)"
            )
        return "\n".join(lines)
