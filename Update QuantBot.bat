@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QuantBot Update
cd /d "%~dp0"

echo ==================================================
echo   QuantBot Update
echo   Holt den aktuellen Stand von GitHub (main)
echo ==================================================
echo.

set "UPDATED=0"
set "VIA="

where git >nul 2>nul
if errorlevel 1 goto ZIP

if not exist ".git" goto ZIP

echo [1/3] Git: lade main von GitHub...
rem Turn off git's automatic housekeeping. On OneDrive/Dropbox folders the
rem prune step cannot delete locked files in .git\objects and shows a
rem "Deletion of directory ... failed. Should I try again? (y/n)" prompt.
rem Disabling gc makes the update non-interactive and reliable.
git config gc.auto 0 >nul 2>nul
git config maintenance.auto false >nul 2>nul
git remote -v
git -c gc.auto=0 fetch origin main
if errorlevel 1 (
  echo Git-Fetch fehlgeschlagen. Versuche ZIP-Download...
  goto ZIP
)

rem Drop local branch state; always track origin/main.
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
set "VIA=git"
goto VERIFY

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
set "VIA=zip"

rem ZIP does not replace .git — realign the repo pointer to origin/main when possible.
where git >nul 2>nul
if errorlevel 1 goto VERIFY
if not exist ".git" goto VERIFY
echo [1b] Git-Zeiger nach ZIP auf main setzen...
git config gc.auto 0 >nul 2>nul
git -c gc.auto=0 fetch origin main >nul 2>nul
git checkout -B main origin/main >nul 2>nul
git reset --hard origin/main >nul 2>nul

:VERIFY
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
set "BRANCH="
set "HEAD="
if exist ".git" (
  for /f "delims=" %%H in ('git rev-parse --short HEAD 2^>nul') do set "HEAD=%%H"
  for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
)

rem Fingerprint: multi-sport merge must be present on a successful main update.
set "OK_FILES=1"
if not exist "src\quantbot\data\basketball.py" set "OK_FILES=0"
findstr /C:"\"settings\": t(\"page.settings\"" "src\quantbot\dashboard\app.py" >nul 2>nul
if errorlevel 1 set "OK_FILES=0"

if "%UPDATED%"=="1" if "%OK_FILES%"=="1" (
  echo ==================================================
  echo   Update fertig. ^(via %VIA%^)
  echo ==================================================
) else (
  echo ==================================================
  echo   Update FEHLGESCHLAGEN oder unvollstaendig.
  echo ==================================================
  set "UPDATED=0"
)

if defined HEAD (
  echo   Git-Stand: %HEAD%
  echo   Branch:    %BRANCH%
)

if /I not "%BRANCH%"=="main" if defined BRANCH (
  echo.
  echo   WARNUNG: Branch ist nicht "main" ^(aktuell: %BRANCH%^).
  echo   Du laeufst vermutlich noch einen alten Claude-/Feature-Branch.
  echo   Bitte in diesem Ordner ausfuehren:
  echo     git fetch origin main
  echo     git checkout -B main origin/main
  echo     git reset --hard origin/main
  echo   Danach Update erneut starten.
)

if "%OK_FILES%"=="0" (
  echo.
  echo   WARNUNG: Erwartete main-Dateien fehlen ^(z.B. basketball.py / settings^).
  echo   Update hat den Codestand nicht korrekt ueberschrieben.
  echo   OneDrive/Datei-Sperren? QuantBot schliessen, dann Update erneut.
)

if exist ".venv\Scripts\python.exe" (
  for /f "delims=" %%V in ('".venv\Scripts\python.exe" -c "import quantbot; print(quantbot.__version__)" 2^>nul') do echo   Version:   %%V
)
echo.
echo Bitte QuantBot komplett schliessen und neu starten
echo ^(schwarzes Fenster zu, dann "Start QuantBot.bat"^).
echo Im Dashboard: Sport-Filter Basketball/NBA und Seite Einstellungen.
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
