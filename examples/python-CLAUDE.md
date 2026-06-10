# Example: Python project with PQA
Default to /pqa for non-trivial work. Branch with pqa-generator's Python language pack; verify
with the language-verification skill (pytest, ruff, pyright strict). Allocate one branch to the
unknown (sync vs async, dataclass vs protocol, batch vs stream). Hold the invariant: nothing
merges without passing the verifier; conviction explores, evidence accepts.
