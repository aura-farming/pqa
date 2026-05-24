"""All configuration loaded from environment. No secrets in code.

PQA runs every agent on Opus (latest) by design — maximum capability per branch. The
`model: opus` alias in each agent's frontmatter tracks the newest Opus automatically.

No API key: PQA installs into Claude Code (project/user scope) and its agents run through
Claude Code's subagents on the user's existing subscription. The budget value is a usage
guardrail, not an API bill — meaningful mainly for API/usage-based access.
"""

from __future__ import annotations

import os

BRANCHES: int = int(os.getenv("PQA_BRANCHES", "3"))
VERIFY_TESTS: bool = os.getenv("PQA_VERIFY_TESTS", "0") == "1"
MODEL: str = os.getenv("PQA_MODEL", "opus")  # every agent runs on Opus (latest)
RUN_BUDGET_USD: float = float(os.getenv("PQA_RUN_BUDGET_USD", "15"))  # hard cap per run
MEMORY_DB: str = os.getenv("PQA_MEMORY_DB", ".claude/hooks/memory/pqa_memory.db")
