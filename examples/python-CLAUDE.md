# Example: Python project with PQA
Default to /pqa for non-trivial work. Branch with pqa-python-brancher; verify with the
python-verification skill (pytest, ruff, pyright strict, mutmut). Allocate one branch to the
unknown (sync vs async, dataclass vs protocol, batch vs stream). Hold the invariant: nothing
merges without passing the verifier; conviction explores, evidence accepts.
