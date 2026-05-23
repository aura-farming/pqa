#!/usr/bin/env python3
"""UserPromptSubmit gate. On build-intent prompts, injects the PQA dual-frame protocol
into context so the model loads BOTH a research frame and a self-eval frame before
branching — and treats their disagreement as the first collision.

Soft gate: it injects guidance (stdout is added to context) rather than blocking, so it
never gets in the way of quick questions. It only fires on prompts that look like a build.
Stdlib only; always exits 0.
"""
import json
import re
import sys

BUILD_INTENT = re.compile(
    r"\b(build|implement|design|architect|create|refactor|write|add|fix|optimi[sz]e|"
    r"solve|/pqa|/superpose)\b",
    re.IGNORECASE,
)

PROTOCOL = (
    "[PQA] This looks like a build task. Before producing a solution, run the dual-frame load:\n"
    "1) RESEARCH frame — what current docs/sources say is correct (use pqa-researcher).\n"
    "2) SELF-EVAL frame — what is true in THIS context, independent of best practice.\n"
    "State both, and name where they disagree — that gap is the first branching axis.\n"
    "Then superpose divergent branches, attack them (pqa-adversary), and collapse on the "
    "verifier's evidence. Conviction protects a branch from pruning, never from tests."
)


def read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}


def main() -> int:
    payload = read_payload()
    prompt = str(payload.get("prompt", ""))
    if BUILD_INTENT.search(prompt):
        # stdout from a UserPromptSubmit hook is added to the model's context.
        try:
            print(PROTOCOL)
        except BrokenPipeError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
