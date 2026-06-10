---
name: conviction-signalling
description: Use when flagging branch conviction or calibrating instinct against outcomes.
---

# Conviction Signalling

Conviction ("the wormhole") is the harness's honest channel for instinct: a generator
that believes in a non-obvious branch can say so, and the system protects that branch
from early pruning — without ever letting belief decide acceptance. Effect on
exploration, never on acceptance: that line is the invariant the design rides on.

## The signal

One line, machine-parsed (regex in `pqa/signals.py`; byte-identical copy in
`hooks/precipitate_capture.py` — change both together):

```
conviction: high, basis: <one sentence naming the non-obvious reason this works>
```

- Levels: `high | medium | low`. Only `high` protects from early pruning
  (`Conviction.protects_from_pruning`).
- `basis` is mandatory and must name a mechanism: "burst absorption beats rejection
  for this producer mix" calibrates; "feels clean" does not.
- The branch digest carries the same `conviction`/`basis` fields, so the orchestrator,
  the capture hook, and the engine all see one story.

## What conviction buys — and what it never buys

| Stage | Effect of `conviction: high` |
|---|---|
| collision (early pruning) | protected — cannot be dropped for "looking weak" before attack completes |
| adversary | attacked HARDER, not softer — calibration needs the stress |
| verification | nothing; the verifier does not read it |
| collapse | nothing; `BranchResult.conviction` is telemetry, and `scripts/check_invariant.py` statically forbids it from entering `_rank_key` |
| taxonomy / calibration | everything — signals joined to outcomes are the moat |

## Protocol

1. **Flag only when real.** Use `high` only if you would defend the branch under
   attack. Faked conviction is exposed by calibration and the harness learns to
   discount you — the signal's entire value is its honesty.
2. **Record at capture:** `pqa.memory.record_signal(conn, session, level, basis,
   branch=...)` — the precipitate-capture hook does this automatically for subagent
   transcripts that contain the conviction line.
3. **Back-fill outcomes after collapse:** `update_signal_outcome(conn, signal_id,
   survived=..., verified=..., won=...)`. A finished run with outcome-less signals is
   a calibration loop with no data — never leave them unfilled.
4. **Read the calibration before trusting the instinct.** `pqa-self-reflector` joins
   signals to outcomes and emits P(win | conviction=high) vs P(win | no signal). That
   number — not the feeling — is the empirical answer to "do hunches mean anything
   here?"
5. **Treat high-conviction deaths as the prize.** "High conviction, failed
   verification" is the single most valuable row the system records; the failure
   taxonomy carries conviction per row — tag it faithfully.

## Worked example

b2 (scout) digests back: `conviction: high, basis: callers can shed load better than
any limiter because only they know what's droppable.`

- Collision: another branch looks cleaner early; b2 is protected from pruning, so the
  attack proceeds on all branches.
- Adversary hits b2 hardest (per protocol). Finding: "assumes every caller implements
  shedding; the legacy cron client cannot."
- Verifier: b2 fails one integration test on the legacy-client path —
  `verified: false`.
- Collapse: b2 is out; conviction never consulted. b0 wins.
- Records: signal row (`high`, basis verbatim); outcome `survived=true,
  verified=false, won=false`; failure row carries `conviction: high`.

Five runs later the calibration table shows high-conviction branches winning at 2× the
no-signal base rate in this repo — the instinct is real here, and protecting it next
spawn is justified by data. Or it shows 0.5× — and the harness starts discounting.
Either answer is the system working as designed.

## Anti-patterns

- **Conviction as argument.** Quoting the basis to the judge at collapse is a contract
  violation; collapse ranks evidence only.
- **Reflex-high.** Flagging every branch high destroys pruning protection (everything
  protected = nothing protected) and ruins your calibration curve.
- **Vibes basis.** A basis that names no mechanism can only be counted, never
  calibrated.
- **Orphan signals.** Signals without back-filled outcomes are dead weight that biases
  every future read toward "unknown."
- **Softening the death.** Recording a high-conviction failure as "almost worked" is
  exactly the instinct-vs-reality divergence the signal exists to measure.
