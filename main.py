"""Thin CLI mirror of /pqa for non-interactive / CI use.

Bootstraps config and prints the task framing PQA will run. The interactive path is the
/pqa slash command inside Claude Code; this entry point exists for scripted runs and the
Agent SDK. Heavy lifting lives in the pqa/ package and the .claude/ subagents.
"""

from __future__ import annotations

import sys

from config import settings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('usage: python main.py "<task description>"', file=sys.stderr)
        return 1
    task = " ".join(argv[1:])
    print(f"PQA run | branches={settings.BRANCHES} | task: {task}")
    print("Interactive path: open Claude Code in this repo and run  /pqa", task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
