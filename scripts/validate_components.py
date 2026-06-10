#!/usr/bin/env python3
"""PQA component validator — the generator, inverted (roadmap §6.1).

Components are hand-written; their content is the product. This script proves the
surface stays disciplined instead of stamping it into existence:

- agents/*.md   — frontmatter complete; name matches filename; description ≤ 15 words
                  (the per-session token tax); model matches the routing table
                  (Fable 5 for coding/judgment, sonnet mechanical, haiku bookkeeping —
                  operator directive 2026-06-10).
- commands/*.md — description ≤ 15 words; body stays thin (≤ 60 lines).
- skills/*/     — SKILL.md present, frontmatter parses, name matches the directory,
                  description ≤ 15 words, body ≥ 60 non-blank lines (skills are deep
                  playbooks, not stubs — roadmap §6.2).
- docs/catalog.json — regenerated FROM the files (`--write-catalog`), and validated
                  equal otherwise, so the catalog can never drift from disk.

Run:  python3 scripts/validate_components.py            # validate, exit 1 on violations
      python3 scripts/validate_components.py --write-catalog
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_DESCRIPTION_WORDS = 15
MAX_COMMAND_BODY_LINES = 60
MIN_SKILL_BODY_LINES = 60
VALID_MODELS = frozenset({"fable", "opus", "sonnet", "haiku"})

# Routing table (operator directive 2026-06-10 + roadmap §5.1): Fable 5 does the
# actual coding and the quality-critical judgment; cheaper tiers do everything else.
# Every agent file must appear here — adding an agent means making a routing decision.
AGENT_MODEL_ROUTING: dict[str, str] = {
    # coding + judgment-critical — the work that decides output quality
    "pqa-generator": "fable",
    "pqa-unknown-scout": "fable",
    "pqa-adversary": "fable",
    "pqa-collapse-judge": "fable",
    "pqa-baseline-runner": "fable",  # fair control: same model as the generators
    # mechanical execution
    "pqa-orchestrator": "sonnet",
    "pqa-frame-loader": "sonnet",
    "pqa-verifier": "sonnet",
    "pqa-reconciler": "sonnet",
    "pqa-self-reflector": "sonnet",
    "pqa-instinct-synthesizer": "sonnet",
    # bookkeeping
    "pqa-memory-curator": "haiku",
    "pqa-failure-taxonomist": "haiku",
    "pqa-eval-runner": "haiku",
}

_AGENT_REQUIRED_KEYS = ("name", "description", "tools", "model")


def parse_frontmatter(text: str, label: str) -> tuple[dict[str, str], list[str]]:
    """Parse the `--- ... ---` block into key/value pairs. Returns (fields, violations)."""
    if not text.startswith("---\n"):
        return {}, [f"{label}: missing frontmatter"]
    end = text.find("\n---", 4)
    if end == -1:
        return {}, [f"{label}: unterminated frontmatter"]
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith(" "):
            continue  # continuation/empty lines are not key material
        if ":" not in line:
            return fields, [f"{label}: malformed frontmatter line {line!r}"]
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, []


def _check_description(value: str, label: str) -> list[str]:
    words = len(value.split())
    if words > MAX_DESCRIPTION_WORDS:
        return [
            f"{label}: description is {words} words (max {MAX_DESCRIPTION_WORDS}) — "
            "descriptions are a per-session token tax"
        ]
    if not value:
        return [f"{label}: empty description"]
    return []


def _check_agent(path: Path) -> list[str]:
    label = f"agents/{path.name}"
    fields, violations = parse_frontmatter(path.read_text(encoding="utf-8"), label)
    for key in _AGENT_REQUIRED_KEYS:
        if key not in fields:
            violations.append(f"{label}: missing frontmatter key {key!r}")
    if not violations:
        if fields["name"] != path.stem:
            violations.append(f"{label}: name {fields['name']!r} != filename {path.stem!r}")
        violations += _check_description(fields["description"], label)
        model = fields["model"]
        if model not in VALID_MODELS:
            violations.append(f"{label}: unknown model {model!r}")
        routed = AGENT_MODEL_ROUTING.get(fields["name"])
        if routed is None:
            violations.append(
                f"{label}: agent not in the routing table — adding an agent means "
                "making a model-routing decision in validate_components.py"
            )
        elif model != routed:
            violations.append(f"{label}: model {model!r} violates routing (expected {routed!r})")
    return violations


def _check_command(path: Path) -> list[str]:
    label = f"commands/{path.name}"
    text = path.read_text(encoding="utf-8")
    fields, violations = parse_frontmatter(text, label)
    if "description" not in fields:
        violations.append(f"{label}: missing frontmatter key 'description'")
    else:
        violations += _check_description(fields["description"], label)
    body_lines = len(text.splitlines())
    if body_lines > MAX_COMMAND_BODY_LINES:
        violations.append(
            f"{label}: {body_lines} lines (max {MAX_COMMAND_BODY_LINES}) — commands are "
            "thin pointers; depth belongs in the agent"
        )
    return violations


def _skill_body_lines(text: str) -> int:
    """Non-blank lines after the frontmatter — the 'real content' the depth gate counts."""
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            body = text[end + 4 :]
    return sum(1 for line in body.splitlines() if line.strip())


def _check_skill(skill_dir: Path) -> list[str]:
    label = f"skills/{skill_dir.name}"
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{label}: missing SKILL.md"]
    text = skill_md.read_text(encoding="utf-8")
    fields, violations = parse_frontmatter(text, label)
    if fields.get("name", skill_dir.name) != skill_dir.name:
        violations.append(f"{label}: name {fields.get('name')!r} != directory name")
    if "description" not in fields:
        violations.append(f"{label}: missing frontmatter key 'description'")
    else:
        violations += _check_description(fields["description"], label)
    body_lines = _skill_body_lines(text)
    if body_lines < MIN_SKILL_BODY_LINES:
        violations.append(
            f"{label}: {body_lines} non-blank body lines (min {MIN_SKILL_BODY_LINES}) — "
            "skills are deep playbooks, not stubs"
        )
    return violations


def _entries(root: Path, sub: str) -> list[Path]:
    base = root / sub
    if not base.exists():
        return []
    if sub == "skills":
        return sorted(p for p in base.iterdir() if p.is_dir())
    return sorted(base.glob("*.md"))


def files_catalog(root: Path) -> dict[str, list[dict[str, str]]]:
    """The catalog as derived from the files on disk — the only source of truth."""

    def fm(path: Path) -> dict[str, str]:
        fields, _ = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
        return fields

    return {
        "agents": [
            {
                "name": p.stem,
                "description": fm(p).get("description", ""),
                "model": fm(p).get("model", ""),
            }
            for p in _entries(root, "agents")
        ],
        "commands": [
            {"name": p.stem, "description": fm(p).get("description", "")}
            for p in _entries(root, "commands")
        ],
        "skills": [
            {"name": d.name, "description": fm(d / "SKILL.md").get("description", "")}
            for d in _entries(root, "skills")
            if (d / "SKILL.md").exists()
        ],
    }


def validate(root: Path) -> list[str]:
    violations: list[str] = []
    for path in _entries(root, "agents"):
        violations += _check_agent(path)
    for path in _entries(root, "commands"):
        violations += _check_command(path)
    for skill_dir in _entries(root, "skills"):
        violations += _check_skill(skill_dir)

    catalog_path = root / "docs" / "catalog.json"
    derived = files_catalog(root)
    if not catalog_path.exists():
        violations.append("docs/catalog.json: missing — run --write-catalog")
    else:
        try:
            recorded = json.loads(catalog_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            recorded = None
            violations.append(f"docs/catalog.json: unparseable ({exc})")
        if recorded is not None and recorded != derived:
            violations.append(
                "docs/catalog.json: drift from the files on disk — run --write-catalog"
            )
    return violations


def write_catalog(root: Path) -> Path:
    catalog_path = root / "docs" / "catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(files_catalog(root), indent=2) + "\n", encoding="utf-8")
    return catalog_path


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    if "--write-catalog" in argv:
        path = write_catalog(root)
        print(f"wrote {path}")
    violations = validate(root)
    if violations:
        for violation in violations:
            print(f"FAIL {violation}", file=sys.stderr)
        return 1
    catalog = files_catalog(root)
    print(
        f"ok: {len(catalog['agents'])} agents, {len(catalog['commands'])} commands, "
        f"{len(catalog['skills'])} skills validated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
