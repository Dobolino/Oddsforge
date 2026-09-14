@echo off
title QuantBot
cd /d "%~dp0"

rem --- Find Python ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto NOPY

rem --- First run: set up automatically ---
if not exist ".venv\Scripts\python.exe" (
  echo ==================================================
  echo   Erste Einrichtung. Das dauert ein paar Minuten.
  echo   Bitte warten, das Fenster nicht schliessen.
  echo ==================================================
  %PY% -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e .
)

echo.
echo Starte QuantBot. Der Browser oeffnet sich gleich von selbst.
echo Zum Beenden dieses Fenster schliessen.
echo.
for /f "delims=" %%V in ('".venv\Scripts\python.exe" -c "import quantbot; print(quantbot.__version__)" 2^>nul') do echo Version: %%V
echo.
".venv\Scripts\python.exe" -m streamlit run "src\quantbot\dashboard\app.py" --server.headless true
goto END

:NOPY
echo.
echo Python ist noch nicht installiert.
echo Ich oeffne jetzt die Download-Seite.
echo Bitte Python installieren und dabei unten das Haekchen
echo   "Add python.exe to PATH"
echo setzen. Danach diese Datei erneut doppelklicken.
echo.
start "" https://www.python.org/downloads/windows/

:END
echo.
pause
