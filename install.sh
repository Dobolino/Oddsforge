#!/bin/bash
# QuantBot installer for macOS / Linux.
# Usage:  bash install.sh

set -euo pipefail
cd "$(dirname "$0")"

echo "QuantBot installer"
echo

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
      PY="$cand"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.11+ wurde nicht gefunden."
  echo "Installiere z. B. von https://www.python.org/downloads/macos/ oder: brew install python@3.12"
  exit 1
fi

echo "Using Python: $($PY --version)"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment (.venv) ..."
  "$PY" -m venv .venv
fi

echo "Upgrading pip ..."
.venv/bin/python -m pip install --quiet --upgrade pip
echo "Installing QuantBot and dependencies (this can take a few minutes) ..."
.venv/bin/python -m pip install --quiet -e ".[dev]"

echo "Verifying installation ..."
.venv/bin/python -m quantbot.cli info 2>/dev/null || .venv/bin/quantbot info 2>/dev/null || true

chmod +x "Start QuantBot.command" "Update QuantBot.command" 2>/dev/null || true

echo
echo "Done. To use QuantBot:"
echo "  • Doppelklick auf \"Start QuantBot.command\"  (einfachster Weg)"
echo "  • oder im Terminal:"
echo "      source .venv/bin/activate"
echo "      quantbot dashboard"
