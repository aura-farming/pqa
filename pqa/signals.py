"""Conviction ('wormhole') signal parsing.

A generator may flag a branch with a line like:
    conviction: high, basis: <one non-obvious sentence>
This is instinct telemetry. It protects a branch from early pruning during collision; it
never promotes a branch past verification. Parsing it is all this module does — the policy
('protect, don't exempt') lives in the orchestrator and collapse logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# NOTE: kept byte-identical to hooks/precipitate_capture.py:CONVICTION. The hook cannot
# import this module (hooks are stdlib-only and must run without the pqa package on the
# path), so the regex is intentionally duplicated — change both together.
_PATTERN = re.compile(r"conviction:\s*(high|medium|low)\s*,\s*basis:\s*(.+)", re.IGNORECASE)
_LEVELS = {"high", "medium", "low"}


@dataclass(frozen=True)
class Conviction:
    level: str  # high | medium | low
    basis: str  # the stated non-obvious reason

    @property
    def protects_from_pruning(self) -> bool:
        """High-conviction branches are shielded from early pruning in collision."""
        return self.level == "high"


def parse_conviction(text: str) -> Conviction | None:
    match = _PATTERN.search(text or "")
    if not match:
        return None
    level = match.group(1).lower()
    if level not in _LEVELS:
        return None
    return Conviction(level=level, basis=match.group(2).strip())
