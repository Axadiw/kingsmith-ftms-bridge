#!/usr/bin/env bash
# Install Kingsmith FTMS Bridge: system dependencies (optional) and Python package.
# Usage: ./install.sh [--system-deps]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SYSTEM_DEPS=false
for arg in "$@"; do
  case "$arg" in
    --system-deps) SYSTEM_DEPS=true ;;
    -h|--help)
      echo "Usage: $0 [--system-deps]"
      echo "  --system-deps  Install system packages (bluez, python3-pip, python3-venv) via apt (sudo)."
      exit 0
      ;;
  esac
done

echo "=== Kingsmith FTMS Bridge - Install ==="

# Optional: install system dependencies
if [ "$SYSTEM_DEPS" = true ]; then
  if command -v apt-get &>/dev/null; then
    echo "Installing system dependencies (bluez, python3-pip, python3-venv)..."
    sudo apt-get update
    sudo apt-get install -y bluez python3-pip python3-venv
  else
    echo "Warning: apt-get not found; skip system deps or install bluez and Python 3.10+ manually."
  fi
else
  echo "Skipping system deps. Run with --system-deps to install bluez, python3-pip, and python3-venv."
fi

# Prefer Python 3.10+
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
  if command -v "$cmd" &>/dev/null; then
    v=$("$cmd" -c 'import sys; print(sys.version_info.major, sys.version_info.minor)' 2>/dev/null || true)
    if [ -n "$v" ]; then
      maj=${v%% *}
      min=${v##* }
      if [ "$maj" -ge 3 ] 2>/dev/null && [ "${min:-0}" -ge 10 ] 2>/dev/null; then
        PYTHON="$cmd"
        break
      fi
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Error: Python 3.10+ not found. Install it and run this script again."
  exit 1
fi

echo "Using: $PYTHON ($($PYTHON --version 2>&1))"

# Prefer venv in project dir; recreate if broken (e.g. missing activate)
VENV_DIR="$SCRIPT_DIR/.venv"
ACTIVATE="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE" ]; then
  if [ -d "$VENV_DIR" ]; then
    echo "Removing incomplete or broken .venv ..."
    rm -rf "$VENV_DIR"
  fi
  echo "Creating virtual environment in $VENV_DIR ..."
  "$PYTHON" -m venv "$VENV_DIR" || {
    echo "Error: Failed to create virtual environment. Try: sudo apt install python3-venv python3.12-venv"
    exit 1
  }
  [ -f "$ACTIVATE" ] || {
    echo "Error: venv was created but $ACTIVATE is missing."
    exit 1
  }
fi

# Activate and install
echo "Installing Python dependencies and package..."
# shellcheck source=/dev/null
source "$ACTIVATE"
pip install --upgrade pip
pip install -e .

echo ""
echo "Install done. Activate the venv and run:"
echo "  source $VENV_DIR/bin/activate"
echo "  kingsmith-ftms-bridge"
echo "Or use ./run.sh to start the bridge."
