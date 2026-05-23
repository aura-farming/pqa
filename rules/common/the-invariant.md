# The PQA invariant (non-negotiable)
Nothing reaches a merge without passing the verifier. Conviction, elegance, and "it feels right"
change *what is explored*, never *what is accepted*. A high-conviction branch that fails tests is
a recorded failure, not a shipped feature. No code path may bypass the verifier; CI enforces this.
