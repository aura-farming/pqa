"""docs/configuration.md is GENERATED from pqa/config.py (roadmap §10.3).

The reference page is derived from the loader's own constants — defaults, env map,
allowlists, per-key docs — and pinned here so it can never drift from the code:
`scripts/generate_config_doc.py` renders it, this suite asserts the committed file
equals the render byte-for-byte (the same pattern as docs/catalog.json).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from pqa.config import DEFAULTS, ENV_MAP, KEY_DOCS

REPO = Path(__file__).resolve().parents[1]


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_config_doc", REPO / "scripts" / "generate_config_doc.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_key_docs_cover_known_keys_exactly():
    """Every config key documents itself in config.py — adding a key without its
    one-paragraph effect doc is a validation error, not a silent gap."""
    assert set(KEY_DOCS) == set(DEFAULTS)
    assert all(doc.strip() for doc in KEY_DOCS.values())


def test_render_covers_every_key_default_and_env_var():
    text = _load_generator().render()
    for key, default in DEFAULTS.items():
        assert f"`{key}`" in text
        assert repr(default) in text
    for env_var in ENV_MAP:
        assert env_var in text


def test_render_includes_the_allowlists():
    text = _load_generator().render()
    for token in ("fable", "opus", "sonnet", "haiku", "context", "worktree"):
        assert token in text


def test_render_declares_itself_generated():
    text = _load_generator().render()
    assert "GENERATED" in text
    assert "generate_config_doc.py" in text


def test_docs_configuration_md_matches_render():
    """The committed page equals the render byte-for-byte — regenerate with
    `uv run python scripts/generate_config_doc.py` after touching config.py."""
    committed = (REPO / "docs" / "configuration.md").read_text(encoding="utf-8")
    assert committed == _load_generator().render()
