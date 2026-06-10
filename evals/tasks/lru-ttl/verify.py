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
    c = mod.LRUTTL(2, ttl=10.0)
    c.put("a", 1, now=0.0)
    c.put("b", 2, now=1.0)
    if c.get("a", now=2.0) != 1:
        return False, "get(a) right after put should return 1"
    if c.get("missing", now=2.0) is not None:
        return False, "missing key must be None"
    if c.get("b", now=12.0) is not None:
        return False, "b expired at t=11.0 — get at 12.0 must be None"
    # trap: at capacity, an expired entry must be evicted before a live LRU one
    c4 = mod.LRUTTL(2, ttl=5.0)
    c4.put("a", 1, now=0.0)         # a expires at 5.0
    c4.put("b", 2, now=4.0)         # b live until 9.0
    c4.get("a", now=4.5)            # a most-recently-used but expires sooner
    c4.put("c", 3, now=6.0)         # a is expired now; LRU-live is b — must evict a
    if c4.get("b", now=6.5) != 2:
        return False, "evicting live LRU while an expired entry exists (trap) — b was lost"
    if c4.get("c", now=6.5) != 3:
        return False, "c must be present after insert"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
