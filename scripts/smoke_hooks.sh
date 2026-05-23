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

exit $fail
