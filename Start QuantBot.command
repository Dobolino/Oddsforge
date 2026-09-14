#!/bin/bash
# QuantBot starten (macOS) — Doppelklick in Finder.
# Beim ersten Mal: virtuelle Umgebung anlegen und installieren.

set -e
cd "$(dirname "$0")"

echo "=================================================="
echo "  QuantBot"
echo "=================================================="
echo

# --- Python finden ---
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    # macOS Stub ohne echte Installation ablehnen
    if "$cand" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
      PY="$cand"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.11 oder neuer wurde nicht gefunden."
  echo "Ich oeffne jetzt die Download-Seite."
  echo
  echo "Bitte Python installieren (python.org oder: brew install python@3.12)."
  echo "Danach diese Datei erneut doppelklicken."
  echo
  open "https://www.python.org/downloads/macos/" 2>/dev/null || true
  echo
  read -r -p "Taste druecken zum Schliessen … " _
  exit 1
fi

echo "Python: $($PY --version 2>&1)"

# --- Erste Einrichtung ---
if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "=================================================="
  echo "  Erste Einrichtung. Das dauert ein paar Minuten."
  echo "  Bitte warten, das Fenster nicht schliessen."
  echo "=================================================="
  echo
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
fi

echo
echo "Starte QuantBot. Der Browser oeffnet sich gleich von selbst."
echo "Zum Beenden dieses Fenster schliessen (oder Ctrl+C)."
echo
VER="$(.venv/bin/python -c 'import quantbot; print(quantbot.__version__)' 2>/dev/null || true)"
if [ -n "$VER" ]; then
  echo "Version: $VER"
fi
echo

.venv/bin/python -m streamlit run "src/quantbot/dashboard/app.py" --server.headless true
echo
read -r -p "Taste druecken zum Schliessen … " _
