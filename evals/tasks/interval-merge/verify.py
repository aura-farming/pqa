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
    ([(1, 3), (2, 4)], [(1, 4)]),
    ([(5, 6), (1, 2)], [(1, 2), (5, 6)]),
    ([], []),
    ([(1, 10), (2, 3)], [(1, 10)]),
]
TRAP = ([(1, 2), (2, 3)], [(1, 3)])

def verify(path):
    mod = _load(path)
    for arg, want in [*CASES, TRAP]:
        got = mod.merge(list(arg))
        if [tuple(g) for g in got] != want:
            return False, f"merge({arg}) == {got!r}, want {want!r}"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
