#!/usr/bin/env bash
# Proves every PQA hook behaves on representative payloads. Used by the invariant CI.
set -uo pipefail
H="hooks"
fail=0
check() { # name expected_exit actual_exit
  if [[ "$2" != "$3" ]]; then echo "FAIL: $1 expected exit $2 got $3"; fail=1
  else echo "ok: $1 (exit $3)"; fi
}

echo '{"tool_input":{"command":"rm -rf / --no-preserve-root"}}' | python3 "$H/security_gate.py"; check "security_gate blocks rm -rf /" 2 $?
echo '{"tool_input":{"command":"git status"}}' | python3 "$H/security_gate.py"; check "security_gate allows safe cmd" 0 $?
echo '{"tool_input":{"file_path":".env"}}' | python3 "$H/secrets_guard.py"; check "secrets_guard blocks .env read" 2 $?
echo '{"tool_input":{"file_path":"pqa/collapse.py"}}' | python3 "$H/secrets_guard.py"; check "secrets_guard allows normal read" 0 $?
echo '{"prompt":"implement a rate limiter"}' | python3 "$H/research_gate.py" >/dev/null; check "research_gate runs on build intent" 0 $?
echo '{"cwd":"'"$PWD"'","tool_input":{"file_path":"README.md"}}' | python3 "$H/verify_loop.py"; check "verify_loop skips non-python" 0 $?
echo '{"cwd":"'"$PWD"'","session_id":"s","transcript_path":"/nonexistent"}' | python3 "$H/precipitate_capture.py"; check "precipitate_capture never blocks" 0 $?

# kill-switch contract: security hooks need the double opt-in; non-security a single flag
PQA_DISABLED_HOOKS=security_gate PQA_ALLOW_UNSAFE=1 sh -c 'echo "{\"tool_input\":{\"command\":\"rm -rf /\"}}" | python3 "'"$H"'/security_gate.py"'; check "security_gate honours double opt-in" 0 $?
PQA_DISABLED_HOOKS=security_gate sh -c 'echo "{\"tool_input\":{\"command\":\"rm -rf /\"}}" | python3 "'"$H"'/security_gate.py"'; check "security_gate ignores single flag (still blocks)" 2 $?
PQA_DISABLED_HOOKS=research_gate sh -c 'echo "{\"prompt\":\"implement a rate limiter\"}" | python3 "'"$H"'/research_gate.py"'; check "research_gate disabled by single flag" 0 $?

# secrets_guard: a dangling symlink (target removed) must fail closed, not slip through
SLINK_DIR="$(mktemp -d)"; ln -s "$SLINK_DIR/gone" "$SLINK_DIR/looks_safe.txt"
echo '{"tool_input":{"file_path":"'"$SLINK_DIR"'/looks_safe.txt"}}' | python3 "$H/secrets_guard.py"; check "secrets_guard blocks dangling symlink" 2 $?
rm -rf "$SLINK_DIR"

exit $fail
