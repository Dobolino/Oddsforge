# QuantBot installer for Windows (PowerShell).
# Usage:  powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

Write-Host "QuantBot installer" -ForegroundColor Cyan

# 1. Find Python
$python = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $python = $cmd; break }
}
if (-not $python) {
    Write-Host "Python was not found. Install Python 3.11+ from python.org and tick 'Add to PATH'." -ForegroundColor Red
    exit 1
}
Write-Host ("Using Python: " + (& $python --version))

# 2. Create the virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv) ..."
    & $python -m venv .venv
}

# 3. Install QuantBot into the environment
$venvPython = ".\.venv\Scripts\python.exe"
Write-Host "Upgrading pip ..."
& $venvPython -m pip install --quiet --upgrade pip
Write-Host "Installing QuantBot and dependencies (this can take a few minutes) ..."
& $venvPython -m pip install --quiet -e ".[dev]"

# 4. Verify
Write-Host "Verifying installation ..."
& $venvPython -m quantbot.cli info

Write-Host ""
Write-Host "Done. To use QuantBot, open a new terminal in this folder and run:" -ForegroundColor Green
Write-Host "    .venv\Scripts\activate"
Write-Host "    quantbot dashboard"
