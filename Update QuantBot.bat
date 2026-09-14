@echo off
title QuantBot Update
cd /d "%~dp0"

where git >nul 2>nul && goto GIT

echo Lade die neueste Version herunter...
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'https://github.com/Dobolino/Oddsforge/archive/refs/heads/main.zip' -OutFile 'update.zip' -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 goto DLFAIL
powershell -NoProfile -Command "Expand-Archive -Force 'update.zip' 'update_tmp'; Copy-Item -Recurse -Force 'update_tmp\Oddsforge-main\*' '.'; Remove-Item -Recurse -Force 'update_tmp','update.zip'"
goto DEPS

:GIT
echo Hole die neueste Version per Git...
git pull
goto DEPS

:DEPS
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -m pip install -e .
echo.
echo Fertig. Du kannst QuantBot jetzt wieder starten (Start QuantBot).
goto END

:DLFAIL
echo.
echo Automatischer Download nicht moeglich.
echo Falls das Repository privat ist, bitte manuell neu als ZIP laden.
start "" https://github.com/Dobolino/Oddsforge

:END
echo.
pause
