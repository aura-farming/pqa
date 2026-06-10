"""Locked verifier — never edited by any arm. Usage: python3 verify.py <solution.py>
Exit 0 = pass, 1 = fail (first failure printed verbatim), 2 = could not load."""
import importlib.util
import sys


def _load(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
import csv, io

CASES = [
    (["a", "b"], "a,b"),
    (["a,b", "c"], '"a,b",c'),
    (["line1\nline2"], '"line1\nline2"'),
    (["", "x"], ",x"),
]
TRAP = (['say "hi"', "x"], '"say ""hi""",x')

def verify(path):
    mod = _load(path)
    for arg, want in [*CASES, TRAP]:
        got = mod.to_csv_row(list(arg))
        if got != want:
            return False, f"to_csv_row({arg!r}) == {got!r}, want {want!r}"
        parsed = next(csv.reader(io.StringIO(got + "\r\n")))
        if parsed != list(arg):
            return False, f"round-trip of {arg!r} via csv.reader gave {parsed!r}"
    return True, "ok"


if __name__ == "__main__":
    try:
        ok, detail = verify(sys.argv[1])
    except Exception as exc:  # candidate failed to load/run
        print(f"infra/load error: {exc}")
        sys.exit(2)
    print(detail)
    sys.exit(0 if ok else 1)
