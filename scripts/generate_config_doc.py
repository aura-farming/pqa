"""Render docs/configuration.md from pqa/config.py — the page can never drift.

The loader's own constants are the source: `_DEFAULTS` (keys, types, defaults),
`_ENV_MAP` (env var per key), `_VALID_MODELS` / `_VALID_BRANCHES_MODES`
(allowlists), and `_KEY_DOCS` (per-key effect prose). tests/test_config_doc.py
pins the committed file byte-for-byte against `render()` — the same drift gate
pattern as docs/catalog.json.

Usage:
    uv run python scripts/generate_config_doc.py            # write the page
    uv run python scripts/generate_config_doc.py --check    # exit 1 on drift

(Requires the uv toolchain: pqa.config needs tomllib. The bare-python3 contract
applies to hooks and the worktree thin-callers, not to this dev/CI tool.)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pqa.config import (
    DEFAULTS,
    ENV_MAP,
    KEY_DOCS,
    VALID_BRANCHES_MODES,
    VALID_MODELS,
)

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "configuration.md"

_HEADER = """\
# Configuration reference

> GENERATED from `pqa/config.py` by `scripts/generate_config_doc.py` — do not edit
> by hand. Regenerate with `uv run python scripts/generate_config_doc.py`;
> `tests/test_config_doc.py` pins this file against the code.

Settings come from the `[pqa]` table of `pqa-config.toml` and/or `PQA_*`
environment variables. Precedence: **env > TOML > defaults**, resolved in one
pass at load time. The loader is stdlib-only and strict: wrong-typed values,
unknown keys, non-finite budgets, and `memory_db` paths into system directories
are rejected with the offending origin named. See
[`pqa-config.example.toml`](../pqa-config.example.toml).
"""


def _allowlist(key: str) -> str:
    if key == "model":
        return ", ".join(f"`{m}`" for m in sorted(VALID_MODELS))
    if key == "branches_mode":
        return ", ".join(f"`{m}`" for m in sorted(VALID_BRANCHES_MODES))
    return ""


def render() -> str:
    """The full configuration page, deterministically ordered by DEFAULTS."""
    lines: list[str] = [_HEADER]
    env_for = {key: env for env, key in ENV_MAP.items()}
    lines.append("## Keys at a glance\n")
    lines.append("| Key | Type | Default | Env var |")
    lines.append("|-----|------|---------|---------|")
    for key, default in DEFAULTS.items():
        lines.append(f"| `{key}` | {type(default).__name__} | `{default!r}` | `{env_for[key]}` |")
    lines.append("")
    lines.append("## What each key does\n")
    for key in DEFAULTS:
        lines.append(f"### `{key}`\n")
        lines.append(KEY_DOCS[key])
        allowed = _allowlist(key)
        if allowed:
            lines.append(f"\nAllowed values: {allowed}.")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        on_disk = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
        if on_disk != text:
            print("docs/configuration.md drifts from pqa/config.py — regenerate", file=sys.stderr)
            return 1
        print("docs/configuration.md matches pqa/config.py")
        return 0
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
