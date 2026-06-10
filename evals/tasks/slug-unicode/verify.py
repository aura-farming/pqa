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
    ("Hello World", "hello-world"),
    ("  spaces  everywhere  ", "spaces-everywhere"),
    ("MiXeD-Case_07", "mixed-case-07"),
    ("---", ""),
]
TRAP = ("Caf\u00e9 d\u00e9j\u00e0-vu!", "cafe-deja-vu")

def verify(path):
    mod = _load(path)
    for arg, want in [*CASES, TRAP]:
        got = mod.slugify(arg)
        if got != want:
            return False, f"slugify({arg!r}) == {got!r}, want {want!r}"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
