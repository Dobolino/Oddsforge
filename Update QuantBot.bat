@echo off
setlocal EnableExtensions
title QuantBot Update
cd /d "%~dp0"

echo ==================================================
echo   QuantBot Update
echo   Holt den aktuellen Stand von GitHub (main)
echo ==================================================
echo.

set "UPDATED=0"

where git >nul 2>nul
if errorlevel 1 goto ZIP

if not exist ".git" goto ZIP

echo [1/3] Git: lade main von GitHub...
git remote -v
git fetch origin main
if errorlevel 1 (
  echo Git-Fetch fehlgeschlagen. Versuche ZIP-Download...
  goto ZIP
)
git checkout -B main origin/main
if errorlevel 1 (
  echo Konnte nicht auf main wechseln. Versuche ZIP-Download...
  goto ZIP
)
git reset --hard origin/main
if errorlevel 1 (
  echo Git-Reset fehlgeschlagen. Versuche ZIP-Download...
  goto ZIP
)
git clean -fd -e .venv -e .env -e "*.bat.local"
set "UPDATED=1"
goto DEPS

:ZIP
echo [1/3] ZIP: lade main von GitHub...
if exist "update.zip" del /f /q "update.zip" >nul 2>nul
if exist "update_tmp" rmdir /s /q "update_tmp" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; " ^
  "try { " ^
  "  Invoke-WebRequest -Uri 'https://github.com/Dobolino/Oddsforge/archive/refs/heads/main.zip' -OutFile 'update.zip' -UseBasicParsing; " ^
  "  if (-not (Test-Path 'update.zip')) { exit 1 }; " ^
  "  Expand-Archive -Force 'update.zip' 'update_tmp'; " ^
  "  $src = Get-ChildItem 'update_tmp' -Directory | Select-Object -First 1; " ^
  "  if (-not $src) { Write-Host 'ZIP enthaelt keinen Ordner'; exit 2 }; " ^
  "  Write-Host ('Quelle: ' + $src.FullName); " ^
  "  Copy-Item -Recurse -Force (Join-Path $src.FullName '*') '.'; " ^
  "  Remove-Item -Recurse -Force 'update_tmp','update.zip' -ErrorAction SilentlyContinue; " ^
  "  exit 0 " ^
  "} catch { Write-Host $_; exit 1 }"

if errorlevel 1 goto DLFAIL
set "UPDATED=1"
goto DEPS

:DEPS
echo.
echo [2/3] Raeume alte Python-Caches...
if exist "src\quantbot" for /d /r "src\quantbot" %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D" >nul 2>nul
if exist ".streamlit\cache" rmdir /s /q ".streamlit\cache" >nul 2>nul

echo [3/3] Installiere Abhaengigkeiten neu...
if not exist ".venv\Scripts\python.exe" (
  echo Keine .venv gefunden. Starte danach einmal "Start QuantBot.bat".
  goto SHOW
)
".venv\Scripts\python.exe" -m pip install -e . --quiet
if errorlevel 1 (
  echo pip install fehlgeschlagen. Bitte "Start QuantBot.bat" einmal laufen lassen.
)

:SHOW
echo.
if "%UPDATED%"=="1" (
  echo ==================================================
  echo   Update fertig.
  echo ==================================================
) else (
  echo Update unklar. Bitte Ausgabe oben pruefen.
)
if exist ".git" (
  for /f "delims=" %%H in ('git rev-parse --short HEAD 2^>nul') do echo   Git-Stand: %%H
  for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do echo   Branch:    %%B
)
if exist ".venv\Scripts\python.exe" (
  for /f "delims=" %%V in ('".venv\Scripts\python.exe" -c "import quantbot; print(quantbot.__version__)" 2^>nul') do echo   Version:   %%V
)
echo.
echo Bitte QuantBot komplett schliessen und neu starten
echo ^(schwarzes Fenster zu, dann "Start QuantBot.bat"^).
echo Im Dashboard links sollte die neue Version stehen.
echo Neu: Seite "Wettschein", Datum mit Button "Auf heute setzen".
goto END

:DLFAIL
echo.
echo Download fehlgeschlagen.
echo Moegliche Ursachen: kein Internet, Repo privat, Firewall.
echo Bitte manuell als ZIP laden und entpacken:
start "" https://github.com/Dobolino/Oddsforge/archive/refs/heads/main.zip

:END
echo.
pause
endlocal
