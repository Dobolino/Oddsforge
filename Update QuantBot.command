#!/bin/bash
# QuantBot aktualisieren (macOS) — Doppelklick in Finder.
# Holt immer den Branch main von GitHub (Git oder ZIP), raeumt Caches, installiert neu.
# ZIP ueberschreibt .git nicht — danach wird der Git-Zeiger auf origin/main gesetzt.

set -u
cd "$(dirname "$0")"

echo "=================================================="
echo "  QuantBot Update"
echo "  Holt den aktuellen Stand von GitHub (main)"
echo "=================================================="
echo

UPDATED=0
VIA=""
REPO_ZIP="https://github.com/Dobolino/Oddsforge/archive/refs/heads/main.zip"

realign_git_to_main() {
  command -v git >/dev/null 2>&1 || return 1
  [ -d ".git" ] || return 1
  git fetch origin main >/dev/null 2>&1 || return 1
  git checkout -B main origin/main >/dev/null 2>&1 || return 1
  git reset --hard origin/main >/dev/null 2>&1 || return 1
  return 0
}

update_via_git() {
  if ! command -v git >/dev/null 2>&1; then
    return 1
  fi
  if [ ! -d ".git" ]; then
    return 1
  fi
  echo "[1/3] Git: lade main von GitHub..."
  git remote -v || true
  if ! git fetch origin main; then
    echo "Git-Fetch fehlgeschlagen. Versuche ZIP-Download..."
    return 1
  fi
  if ! git checkout -B main origin/main; then
    echo "Konnte nicht auf main wechseln. Versuche ZIP-Download..."
    return 1
  fi
  if ! git reset --hard origin/main; then
    echo "Git-Reset fehlgeschlagen. Versuche ZIP-Download..."
    return 1
  fi
  # .venv und .env behalten
  git clean -fd -e .venv -e .env -e "*.command.local" -e "*.bat.local" || true
  UPDATED=1
  VIA=git
  return 0
}

update_via_zip() {
  echo "[1/3] ZIP: lade main von GitHub..."
  rm -f update.zip
  rm -rf update_tmp

  if command -v curl >/dev/null 2>&1; then
    if ! curl -fsSL -o update.zip "$REPO_ZIP"; then
      return 1
    fi
  elif command -v python3 >/dev/null 2>&1; then
    if ! python3 - <<'PY'
import urllib.request
urllib.request.urlretrieve(
    "https://github.com/Dobolino/Oddsforge/archive/refs/heads/main.zip",
    "update.zip",
)
PY
    then
      return 1
    fi
  else
    echo "Weder curl noch python3 verfuegbar fuer den Download."
    return 1
  fi

  mkdir -p update_tmp
  if ! unzip -q update.zip -d update_tmp; then
    echo "ZIP konnte nicht entpackt werden."
    return 1
  fi
  SRC="$(find update_tmp -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [ -z "$SRC" ]; then
    echo "ZIP enthaelt keinen Ordner."
    return 1
  fi
  echo "Quelle: $SRC"
  # Inhalt uebernehmen, lokale Secrets/Umgebung behalten (.git bleibt erhalten!)
  ditto "$SRC" .
  rm -rf update_tmp update.zip
  UPDATED=1
  VIA=zip

  echo "[1b] Git-Zeiger nach ZIP auf main setzen..."
  if realign_git_to_main; then
    echo "Git zeigt jetzt auf origin/main."
  else
    echo "Hinweis: Dateien von main kopiert, Git-Branch konnte nicht umgestellt werden."
  fi
  return 0
}

verify_main_files() {
  [ -f "src/quantbot/data/basketball.py" ] || return 1
  grep -q '"settings": t("page.settings"' src/quantbot/dashboard/app.py 2>/dev/null || return 1
  return 0
}

if ! update_via_git; then
  if ! update_via_zip; then
    echo
    echo "Download fehlgeschlagen."
    echo "Moegliche Ursachen: kein Internet, Repo privat, Firewall."
    echo "Bitte manuell als ZIP laden und entpacken:"
    open "$REPO_ZIP" 2>/dev/null || true
    echo
    read -r -p "Taste druecken zum Schliessen … " _
    exit 1
  fi
fi

echo
echo "[2/3] Raeume alte Python-Caches..."
if [ -d "src/quantbot" ]; then
  find src/quantbot -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
fi
rm -rf .streamlit/cache 2>/dev/null || true

echo "[3/3] Installiere Abhaengigkeiten neu..."
if [ ! -x ".venv/bin/python" ]; then
  echo "Keine .venv gefunden. Starte danach einmal \"Start QuantBot.command\"."
else
  if ! .venv/bin/python -m pip install -e . --quiet; then
    echo "pip install fehlgeschlagen. Bitte \"Start QuantBot.command\" einmal laufen lassen."
  fi
fi

# Ausfuehrbarkeit der Mac-Starter wiederherstellen (ZIP kann +x verlieren)
chmod +x "Start QuantBot.command" "Update QuantBot.command" 2>/dev/null || true

BRANCH=""
HEAD=""
if [ -d ".git" ] && command -v git >/dev/null 2>&1; then
  HEAD="$(git rev-parse --short HEAD 2>/dev/null || true)"
  BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
fi

echo
if [ "$UPDATED" = "1" ] && verify_main_files; then
  echo "=================================================="
  echo "  Update fertig. (via ${VIA})"
  echo "=================================================="
else
  echo "=================================================="
  echo "  Update FEHLGESCHLAGEN oder unvollstaendig."
  echo "=================================================="
  UPDATED=0
fi

if [ -n "$HEAD" ]; then
  echo "  Git-Stand: $HEAD"
  echo "  Branch:    $BRANCH"
fi

if [ -n "$BRANCH" ] && [ "$BRANCH" != "main" ]; then
  echo
  echo "  WARNUNG: Branch ist nicht \"main\" (aktuell: $BRANCH)."
  echo "  Du laeufst vermutlich noch einen alten Claude-/Feature-Branch."
  echo "  Bitte in diesem Ordner ausfuehren:"
  echo "    git fetch origin main"
  echo "    git checkout -B main origin/main"
  echo "    git reset --hard origin/main"
  echo "  Danach Update erneut starten."
fi

if ! verify_main_files; then
  echo
  echo "  WARNUNG: Erwartete main-Dateien fehlen (z.B. basketball.py / settings)."
  echo "  Update hat den Codestand nicht korrekt ueberschrieben."
fi

if [ -x ".venv/bin/python" ]; then
  VER="$(.venv/bin/python -c 'import quantbot; print(quantbot.__version__)' 2>/dev/null || true)"
  if [ -n "$VER" ]; then
    echo "  Version:   $VER"
  fi
fi

echo
echo "Bitte QuantBot komplett schliessen und neu starten"
echo "(Terminal-Fenster zu, dann \"Start QuantBot.command\")."
echo "Im Dashboard: Sport-Filter Basketball/NBA und Seite Einstellungen."
echo
read -r -p "Taste druecken zum Schliessen … " _
