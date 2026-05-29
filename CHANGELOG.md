# Changelog

All notable changes to PQA are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.4] — 2026-05-29

### Security
- **security_gate**: block secret reads via `xxd`/`od`/`hexdump`/`strings`/`dd`/`sed`/`awk`/`grep`/`egrep`/`fgrep`. The previous list only matched `cat`/`less`/`head`/etc., so a byte reader or stream processor (`strings id_rsa`, `xxd .env`, `grep KEY .env`) trivially bypassed the gate. Readers are blocked only when they target a secret path; boundary tests pin the false-positive line.
- **sanitize**: neutralize forged `</UNTRUSTED_RESEARCH>` / open-prefix delimiters embedded in research content, so untrusted web text can no longer close the wrapper early and have following text read as instructions. Non-stripping — the payload stays visible and the forgery is flagged.

### Added
- End-to-end tests for the quantum-jump tie-break through `orchestrator.run()`: a true tie breaks toward the non-incremental branch, and higher coverage still wins (evidence beats the quantum-jump preference — it is the last tiebreak key, not a promotion).

### Fixed
- `scripts/install.sh` no longer instructs users to set `ANTHROPIC_API_KEY` — PQA runs on the Claude Code subscription; no key is needed.
- `pqa/config.py`: corrected the `model` comment that claimed an alias→`MODEL_PRICING` translation which does not exist; documents that `model` is a declared preference not yet wired to dispatch/pricing, and flags the latent `KeyError` trap.

### Changed
- Cross-referenced the conviction regex duplicated between `pqa/signals.py` and the `precipitate_capture` hook (the hook is stdlib-only and cannot import `pqa`, so the duplication is intentional — "change both together").
- Aligned the package version across `pyproject.toml` and the plugin manifests.

## [0.2.3] — 2026-05-28

### Changed
- Plugin manifest: drop `agents`/`hooks`/`rules` from explicit paths (rely on auto-discovery), `mcpServers={}`, container fields expressed as arrays.

## [0.2.2] — 2026-05-28

### Changed
- Plugin manifest: `author` expressed as an object; container fields as arrays.

## [0.2.1] — 2026-05-28

### Fixed
- Plugin made installable by anyone: MIT license, schema-valid manifests.

[0.2.4]: https://github.com/aura-farming/pqa/releases/tag/v0.2.4
[0.2.3]: https://github.com/aura-farming/pqa/compare/v0.2.3...v0.2.4
[0.2.2]: https://github.com/aura-farming/pqa/compare/v0.2.2...v0.2.3
[0.2.1]: https://github.com/aura-farming/pqa/compare/v0.2.1...v0.2.2
