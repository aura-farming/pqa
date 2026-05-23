# Example: Rust project with PQA
Default to /pqa. Branch with pqa-rust-brancher; verify with rust-verification (cargo test,
clippy, miri where relevant). The type system makes topology choices consequential — diverge on
ownership (move vs Rc), state (enum vs trait-object), and sync vs async. Evidence over eloquence.
