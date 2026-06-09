#!/usr/bin/env python3
"""Shared helpers for PQA hooks. Stdlib only; must stay trivially fast (<10ms).

Kill-switch contract (roadmap §4.2 — every gate must be escapable and say how):

  PQA_DISABLED_HOOKS   comma-separated hook names, e.g. "research_gate,verify_loop".
  PQA_ALLOW_UNSAFE=1   additionally required to disable a SECURITY hook
                       (security_gate, secrets_guard). Disabling a safety gate must
                       be a deliberate double opt-in, never a side effect of a broad
                       env var someone exported for a different reason.

Hooks import this as a sibling module (they run as scripts, so their own directory
is on sys.path). Tests exercise hooks via subprocess, which preserves that property.
"""

from __future__ import annotations

import os

SECURITY_HOOKS: frozenset[str] = frozenset({"security_gate", "secrets_guard"})


def is_disabled(hook_name: str) -> bool:
    """True iff the operator has disabled this hook for the session.

    Non-security hooks: listed in PQA_DISABLED_HOOKS → disabled.
    Security hooks: listed AND PQA_ALLOW_UNSAFE=1 → disabled; listing alone is
    ignored (and the hook's block message explains the double opt-in).
    """
    disabled = {
        name.strip().removesuffix(".py")
        for name in os.getenv("PQA_DISABLED_HOOKS", "").split(",")
        if name.strip()
    }
    if hook_name not in disabled:
        return False
    if hook_name in SECURITY_HOOKS:
        return os.getenv("PQA_ALLOW_UNSAFE") == "1"
    return True


def disable_hint(hook_name: str) -> str:
    """One-line operator-facing escape hatch, embedded in every block message.
    A guardrail with no documented override is a trap, not a guardrail."""
    if hook_name in SECURITY_HOOKS:
        return (
            f"(Operator override: PQA_DISABLED_HOOKS={hook_name} plus PQA_ALLOW_UNSAFE=1 "
            "— only inside a sandbox you fully trust.)"
        )
    return f"(Operator override: PQA_DISABLED_HOOKS={hook_name} disables this hook.)"
