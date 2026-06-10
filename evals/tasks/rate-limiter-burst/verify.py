"""Locked verifier — never edited by any arm. Usage: python3 verify.py <solution.py>
Exit 0 = pass, 1 = fail (first failure printed verbatim), 2 = could not load."""
import importlib.util
import sys


def _load(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
CASES = [
    (([(0.0, "a"), (0.1, "a"), (0.2, "a")], 2, 1.0), [True, True, False]),
    (([(0.0, "a"), (0.5, "b"), (0.6, "a")], 1, 1.0), [True, True, False]),
    (([(0.0, "a"), (2.0, "a")], 1, 1.0), [True, True]),
]
TRAP = (([(0.95, "a"), (0.96, "a"), (1.05, "a"), (1.06, "a")], 2, 1.0),
        [True, True, False, False])  # fixed-window resets at t=1.0 and wrongly admits 4

def verify(path):
    mod = _load(path)
    for args, want in [*CASES, TRAP]:
        got = mod.allow(*args)
        if got != want:
            return False, f"allow{args} == {got!r}, want {want!r}"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
