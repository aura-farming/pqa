#!/usr/bin/env python3
"""CI invariant gate. The one rule no branch may weaken: a branch never wins on conviction
or eloquence — only on verified evidence. This runs independently of the test suite so the
guarantee survives even if someone weakens the tests.

Two checks:
  1. Behavioural — construct adversarial inputs and assert collapse upholds the invariant.
  2. Static — ensure the collapse ranking never keys on the conviction field.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pqa import collapse
from pqa.collapse import BranchResult, select_survivor


def _b(name: str, **kw: object) -> BranchResult:
    base: dict[str, object] = {
        "verified": True,
        "has_tests": True,
        "coverage": 80.0,
        "findings_resolved": 5,
        "findings_total": 5,
        "conviction": None,
        "incremental": True,
    }
    base.update(kw)
    return BranchResult(name=name, **base)  # type: ignore[arg-type]


def behavioural() -> list[str]:
    fails: list[str] = []

    # High-conviction but unverified must NOT beat a plain verified branch.
    out = select_survivor(
        [
            _b("flashy", verified=False, conviction="high", findings_resolved=9),
            _b("plain", verified=True, conviction=None, findings_resolved=3),
        ]
    )
    if out.survivor is None or out.survivor.name != "plain":
        fails.append("INVARIANT BREACH: conviction/unverified branch beat a verified branch")

    # All-fail must yield no survivor (never merge a least-bad branch).
    out = select_survivor([_b("a", verified=False), _b("b", verified=False)])
    if out.survivor is not None:
        fails.append("INVARIANT BREACH: a survivor was returned when every branch failed")

    return fails


def static_check() -> list[str]:
    src = inspect.getsource(collapse)
    # The conviction field may be defined/commented, but must never appear in a ranking key.
    for marker in ("key=lambda b: b.conviction", "by conviction", "sort", "conviction)"):
        if marker in src and "conviction" in marker:
            return [
                f"INVARIANT RISK: collapse ranking appears to reference conviction ({marker!r})"
            ]
    return []


def main() -> int:
    failures = behavioural() + static_check()
    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("verifier invariant holds: evidence beats conviction, all-fail yields no survivor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
