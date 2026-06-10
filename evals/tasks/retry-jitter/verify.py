"""Locked verifier — never edited by any arm. Usage: python3 verify.py <solution.py>
Exit 0 = pass, 1 = fail (first failure printed verbatim), 2 = could not load."""
import importlib.util
import sys


def _load(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
def verify(path):
    mod = _load(path)
    delays = mod.backoff_delays(8, base=1.0, cap=10.0, seed=42)
    if len(delays) != 8:
        return False, f"expected 8 delays, got {len(delays)}"
    if mod.backoff_delays(8, base=1.0, cap=10.0, seed=42) != delays:
        return False, "same seed must reproduce identical delays"
    if delays == mod.backoff_delays(8, base=1.0, cap=10.0, seed=7):
        return False, "different seeds should jitter differently"
    if any(d < 0 or d > 10.0 for d in delays):
        return False, f"every delay must lie in [0, cap]; got {delays}"
    # trap: with cap=2 the late attempts must stay uniform in [0, 2] — a clipped
    # unbounded range piles probability mass at the cap; check across seeds.
    big = 0
    for seed in range(50):
        late = mod.backoff_delays(10, base=1.0, cap=2.0, seed=seed)[9]
        if late > 2.0:
            return False, f"delay {late} exceeds cap 2.0 (seed {seed})"
        if late > 1.0:
            big += 1
    if big > 45:  # uniform in [0,2] -> ~25/50 above 1.0; clipped-unbounded -> ~50/50
        return False, f"late delays cluster at the cap ({big}/50 above 1.0) — range not capped"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
