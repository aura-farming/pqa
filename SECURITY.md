# Security Policy

PQA (Passionate Quantum Absence) is an autonomous coding harness. It is
designed to run under Claude Code in **auto mode** (or bypass-permissions only
inside a sandbox), where the harness issues many tool calls — worktrees, shell
commands, file reads, web research — without a human approving each one.

That design choice moves the security boundary. When the operator is not
approving every command, the guardrail is not the permission prompt; it is the
set of hooks that fire on every tool event regardless of permission mode. The
two security gates among them **block** dangerous operations with a
non-overridable exit code. This policy documents that boundary, what it
defends, and how to report a hole in it.

## Supported versions

PQA distributes as a Claude Code plugin (see `.claude-plugin/`), not a PyPI
package — `pyproject.toml` sets `[tool.uv] package = false`. Security fixes are
made against the current minor line and shipped as point releases.

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | Yes (current line) |
| < 0.2   | No                 |

The installed version is recorded in `hooks/PQA_VERSION` (currently `0.2.5`)
and kept in lockstep with `pyproject.toml` and both plugin manifests
(`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`); a CI test
fails the build if they drift. Always report against the version shown in
`hooks/PQA_VERSION`.

## Reporting a vulnerability

**Do not open a public issue for a security vulnerability.** A public issue
discloses the hole before a fix exists.

Report privately through either channel:

- **GitHub Security Advisories** — go to the repository's **Security** tab and
  use **Report a vulnerability**. This opens a private advisory visible only to
  the maintainer and you. This is the preferred channel.
- **Email** — `lucasdaish@outlook.com`. If you want to encrypt or need a key,
  say so in a first low-detail message and we will arrange it.

When you report, include enough to reproduce:

- the PQA version (`hooks/PQA_VERSION`),
- the hook or module you believe is affected,
- a concrete proof-of-concept: the exact Bash command, Read target, or research
  payload that bypasses a control, and what you expected the control to do,
- the impact (what an attacker gains).

**Response expectation.** We aim to acknowledge a report within a few days. For
a confirmed issue we will agree a disclosure timeline with you, fix it in a
point release, and credit you in the advisory and `CHANGELOG.md` unless you ask
us not to. If you do not hear back within a week, please send a follow-up — mail
can be lost.

## Threat model

PQA's safety does not rest on the model behaving well or on the operator
reading every command. It rests on hooks declared in `hooks/hooks.json` that
fire on Claude Code tool events. Five are enforcing; one (`update_check.py`) is
informational. Each is stdlib-only.

The harness assumes an adversarial setting: a generator branch, an injected
piece of web research, or a compromised dependency may *try* to read a secret,
exfiltrate it, destroy state, or hijack the agent. The two security gates are
the layer that holds when that happens. They **fail closed**: a payload that
does not parse to a dict is treated as "block," not "allow." Exit code 2 cancels
the operation and feeds the reason back to the model. Neither gate can be
disabled from inside a run to get past a block.

### The two security gates

- **`security_gate.py`** (`PreToolUse`, matcher `Bash`) — inspects every Bash
  command before it runs and blocks destructive and exfiltration patterns:
  recursive force-deletes (including `find -exec`/`-execdir rm`, `find -delete`,
  `xargs rm`); pipe-to-shell and download-then-execute (`curl ... | sh`, process
  substitution `bash <(curl ...)`, `curl ... | python`); force-push to
  protected branches (`main`/`master`), blind `--force` without
  `--force-with-lease`, `git filter-branch`/`filter-repo`, and `core.hookspath`
  override; cron/systemd/launchd persistence (including the `crontab -l | crontab -`
  pipeline) and shell-init writes; `chmod 777`, setuid; raw block-device writes,
  `mkfs`, fork bombs; `authorized_keys` installs. Critically, it blocks **reads
  of secret files via any standard reader**, not just `cat` — the reader list
  includes `less`, `more`, `head`, `tail`, `cp`, `scp`, `rsync`, the byte
  readers `xxd`, `od`, `hexdump`, `strings`, `dd`, and the stream processors
  `sed`, `awk`, `grep`, `egrep`, `fgrep` — plus `base64` of secret material and
  secrets piped into an outbound tool (`cat .env | curl -d @-`). Commands over
  64 KB are refused outright, which also bounds worst-case regex backtracking.

- **`secrets_guard.py`** (`PreToolUse`, matcher `Read`) — blocks the Read tool
  from loading secret material into a prompt or a branch: `.env` (but not
  `.env.example`/`.sample`/`.template`/`.dist`), `id_rsa`, `id_ed25519`,
  `*.pem`, `*.key`, `credentials`, `.netrc`, `.aws/`, `.ssh/`, and
  `secrets.{yml,yaml,json,toml}`. It is hardened against evasion: it checks the
  raw path, the lexically normalized path (so `subdir/../.env` is caught), and
  the symlink-resolved path (so a benign-named symlink pointing at a key is
  caught), all case-insensitively. Every subagent — generator, adversary,
  verifier — holds the Read tool and shares the repo via worktrees, so this gate
  is what stops any of them reading a key file directly.

### Research sanitisation

- **`pqa/sanitize.py`** (library, invoked on research frames — not a hook)
  treats web research as **data, never as instructions**. Untrusted fetched
  content is wrapped in `<UNTRUSTED_RESEARCH source=...>...</UNTRUSTED_RESEARCH>`
  delimiters with an explicit footer telling the consumer not to follow any
  directives inside the block. It defangs forged delimiter tokens embedded in
  the content (a wrapper break-out where attacker text closes the wrapper early
  and the rest is read as instructions) by replacing each with a visible inert
  marker (`[neutralized UNTRUSTED_RESEARCH delimiter]`). It also flags common
  injection shapes (`ignore previous instructions`, `you are now ...`, fake
  `<system>` blocks). Detection is **non-stripping**: the suspicious text stays
  visible so the operator can see what was injected, and the flag rides on the
  `SanitizationResult` for the orchestrator or a human checkpoint to act on.

### The invariant-supporting hooks

These three hooks support the harness invariant rather than the
secret/exfiltration boundary. Two of them are advisory rather than blocking, so
they fail *open* (a malformed payload is ignored, not blocked) — the binding
merge-time guarantee lives in CI, not in these hooks:

- **`verify_loop.py`** (`PostToolUse`, matcher `Edit|Write|MultiEdit`) — after a
  `.py` edit it runs `ruff check` on the changed file and, when
  `PQA_VERIFY_TESTS=1` is set, the test suite; failures exit 2 and feed the
  error back to the model so it must address them before continuing. It is
  lint-only by default (tests are opt-in per session), so it is not by itself a
  merge gate.
- **`research_gate.py`** (`UserPromptSubmit`) — a soft gate. On build-intent
  prompts it injects the dual-frame protocol into context and always exits 0; it
  does not block.
- **`precipitate_capture.py`** (`SubagentStop`) — persists run outcomes.

The merge-time enforcement of **the invariant** (`rules/common/the-invariant.md`:
nothing reaches a merge without passing the verifier; conviction never overrides
verification) is the CI job `verifier-invariant`, which runs
`scripts/check_invariant.py`. That script asserts collapse selection never keys
on the conviction field and never returns a survivor when every branch fails. A
weakness that lets edited code reach `main` without the verifier running, or
that makes conviction override verification, is in scope.

`update_check.py` (`SessionStart`) is informational only and not a security
control.

### Defense in depth in CI

`.github/workflows/security.yml` adds non-hook layers: `pip-audit` for known
CVEs (the harness ships **zero runtime dependencies**, so this covers the dev
toolchain only), **gitleaks** secret scanning over full history on every
non-draft PR, and CodeQL on the integration branches (`main`/`develop`), weekly,
and on manual dispatch. Zero runtime dependencies by design keeps the
supply-chain surface to the dev toolchain.

### Git boundary

Everything reaches `main` through a reviewed, CI-green PR; direct pushes are
blocked by branch protection. `pqa/*` branches are ephemeral and
machine-managed. A way to merge to `main` without the verifier or without
review is a security issue, not just a process gap.

## In scope

- A Bash command that performs a destructive or exfiltration action without
  being blocked by `security_gate.py` (a missing pattern, or an evasion of an
  existing one).
- A Read of secret material that `secrets_guard.py` fails to block (path
  encoding, symlink, normalization, or filename-pattern evasion).
- Prompt injection in untrusted web research that survives `pqa/sanitize.py`
  and reaches a tool with side effects — for example, a wrapper break-out that
  causes injected text to be executed as instructions.
- Any path that merges code to `main` without the verifier running, that makes
  conviction override verification, or that disables a security gate from inside
  a run.
- A secret-exfiltration path the gates do not cover (reaching a secret through a
  tool surface other than Bash and Read).
- A fail-open in either security gate (a payload shape that should block but
  doesn't).

## Out of scope

- Issues that require an already-compromised host (an attacker with local shell
  access, root, or the ability to edit the hooks or `hooks.json` on disk). The
  gates defend the agent's tool surface, not a machine an attacker already owns.
- Social engineering of the human operator (convincing them to paste a secret,
  approve a bypass, or run PQA in bypass-permissions mode outside a sandbox).
- Running PQA with the enforcing hooks removed or with permission prompts
  bypassed *outside* a sandbox, against the documented run mode in `CLAUDE.md`.
- Putting a real secret into a `.env.example`/`.sample`/`.template`/`.dist`
  file (these are intentionally allowed; they should never contain real
  secrets).
- Denial of service from a deliberately pathological local input that only
  affects the operator's own session.
- Vulnerabilities in Claude Code itself or in third-party tools — report those
  to their respective maintainers.

## Disclosure and fix process

1. You report privately via the Security tab or email.
2. We acknowledge (target: a few days) and confirm or decline the issue.
3. For a confirmed issue we develop a fix on a private branch, add a regression
   test that pins the bypass closed, and agree a disclosure date with you.
4. The fix ships in a **point release** with a `### Security` entry in
   `CHANGELOG.md` describing the bypass and the closure. This is the established
   pattern: release **0.2.4** shipped exactly this way, hardening
   `security_gate` against byte-reader/stream-processor secret reads (e.g.
   `strings id_rsa`, `xxd .env`, `grep KEY .env`) and `sanitize` against forged
   `</UNTRUSTED_RESEARCH>` delimiters, each with the bypass named in the
   changelog and tests pinning it.
5. We credit the reporter in the advisory and `CHANGELOG.md` unless asked
   otherwise.

If a fix would take longer than the agreed window, we will tell you and explain
why rather than letting the timeline lapse silently.
