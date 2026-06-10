# Example: Rust project with PQA
Default to /pqa. Branch with pqa-generator's Rust language pack; verify with the
language-verification skill (cargo test, clippy, miri where relevant). The type system makes topology choices consequential — diverge on
ownership (move vs Rc), state (enum vs trait-object), and sync vs async. Evidence over eloquence.
