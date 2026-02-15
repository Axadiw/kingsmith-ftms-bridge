#!/usr/bin/env bash
# Run Kingsmith FTMS Bridge. Uses .venv in this directory if present.
# Usage: ./run.sh [options]
#   --no-auto     Manual mode (no auto-scan/connect)
#   --port PORT   Web UI port
#   --host HOST   Web bind address

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
fi

exec python3 -m kingsmith_ftms_bridge.main "$@"
