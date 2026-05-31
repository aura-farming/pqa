#!/usr/bin/env bash
# PQA installer. Two manual modes plus the plugin marketplace path.
#   ./scripts/install.sh project   -> installs into ./.claude (this repo/project)
#   ./scripts/install.sh system    -> installs into ~/.claude (all your projects)
# Or, inside Claude Code:  /plugin marketplace add <git-url>  then  /plugin install pqa
set -euo pipefail
MODE="${1:-project}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

case "$MODE" in
  project) DEST="$(pwd)/.claude" ;;
  system)  DEST="$HOME/.claude" ;;
  *) echo "usage: install.sh [project|system]"; exit 1 ;;
esac

echo "Installing PQA ($MODE) -> $DEST"
mkdir -p "$DEST/agents" "$DEST/skills" "$DEST/commands" "$DEST/hooks/memory" "$DEST/rules/pqa"
cp -R "$SRC/agents/." "$DEST/agents/"
cp -R "$SRC/skills/." "$DEST/skills/"
cp -R "$SRC/commands/." "$DEST/commands/"
cp -R "$SRC/hooks/." "$DEST/hooks/"
cp -R "$SRC/rules/." "$DEST/rules/pqa/"
cp "$SRC/CLAUDE.md" "$DEST/PQA-CLAUDE.md"

# rewrite plugin-root hook paths to the install location for manual (non-plugin) installs
python3 - "$DEST" << 'PY'
import json, sys, pathlib
dest = pathlib.Path(sys.argv[1])
hp = dest / "hooks" / "hooks.json"
data = json.loads(hp.read_text())
def fix(obj):
    if isinstance(obj, dict):
        return {k: fix(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace("${CLAUDE_PLUGIN_ROOT}", str(dest))
    return obj
hp.write_text(json.dumps(fix(data), indent=2))
print("  hook paths rewritten to", dest)
PY

# initialise memory
sqlite3 "$DEST/hooks/memory/pqa_memory.db" < "$SRC/hooks/memory/schema.sql" 2>/dev/null \
  && echo "  memory initialised" || echo "  (install sqlite3 to initialise memory; /precipitate will create it on first run)"

echo "Done. Open Claude Code in your project and run /pqa to start."
echo "Note: agents run on Opus — no API key needed (PQA uses your Claude Code subscription); mind the per-run budget (/budget)."
