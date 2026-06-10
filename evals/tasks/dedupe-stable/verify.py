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
    (["a", "b", "a"], ["a", "b"]),
    ([], []),
    (["x"], ["x"]),
]
TRAP = (["Apple", "banana", "APPLE", "Banana", "cherry"], ["Apple", "banana", "cherry"])

def verify(path):
    mod = _load(path)
    for arg, want in [*CASES, TRAP]:
        got = mod.dedupe(list(arg))
        if got != want:
            return False, f"dedupe({arg!r}) == {got!r}, want {want!r}"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
