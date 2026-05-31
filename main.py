"""Thin CLI mirror of /pqa for non-interactive / CI use.

Bootstraps config and prints the task framing PQA will run. The interactive path is the
/pqa slash command inside Claude Code; this entry point exists for scripted runs and the
Agent SDK. Heavy lifting lives in the pqa/ package and the .claude/ subagents.

Reads configuration via pqa.config.load_or_defaults — uses pqa-config.toml in CWD when
present, otherwise built-in defaults + PQA_* env overrides. Strict validation either way.
"""

from __future__ import annotations

import sys

from pqa.config import load_or_defaults


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('usage: python main.py "<task description>"', file=sys.stderr)
        return 1
    task = " ".join(argv[1:])
    try:
        cfg = load_or_defaults()
    except (FileNotFoundError, ValueError, TypeError) as exc:
        print(f"PQA config error: {exc}", file=sys.stderr)
        return 2
    print(
        f"PQA run | branches={cfg.branches} | model={cfg.model} "
        f"| budget=${cfg.run_budget_usd:.2f} | task: {task}"
    )
    print("Interactive path: open Claude Code in this repo and run  /pqa", task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
