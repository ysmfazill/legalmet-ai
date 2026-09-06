$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $PSScriptRoot
$API = Join-Path $ROOT "services\api"

$PY = Join-Path $API ".venv\Scripts\python.exe"

if (-not (Test-Path $PY)) {
    Write-Error "Backend virtualenv not found at $API\.venv"
    exit 1
}

Write-Host ""
Write-Host "== SAFE DEMO RESET ==" -ForegroundColor Cyan
Write-Host "Removing transactional activity and re-seeding DEMO-FOOD..."
Write-Host ""

Push-Location $API

try {
    & $PY -m scripts.reset_demo

    if ($LASTEXITCODE -ne 0) {
        throw "Demo reset failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "== DEMO RESET COMPLETE ==" -ForegroundColor Green