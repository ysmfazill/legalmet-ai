$ErrorActionPreference = "Stop"

$ROOT = Split-Path -Parent $PSScriptRoot
$API = Join-Path $ROOT "services\api"

$FRONTEND_URL = "http://localhost:5173"
$BACKEND_URL = "http://localhost:8000"

$FRESH = $false
$RESET = $false

if ($args -contains "--fresh") {
    $FRESH = $true
}

if ($args -contains "--reset") {
    $RESET = $true
}

Write-Host ""
Write-Host "== METRASIGHT LOCAL DEMO ==" -ForegroundColor Cyan

# ------------------------------------------------------------
# 1. Frontend dependencies
# ------------------------------------------------------------

Write-Host ""
Write-Host "== Frontend dependencies ==" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $ROOT "node_modules"))) {
    Push-Location $ROOT
    try {
        npm install

        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed"
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "node_modules present - skipping npm install"
}

# ------------------------------------------------------------
# 2. Backend virtual environment
# ------------------------------------------------------------

Write-Host ""
Write-Host "== Backend virtualenv ==" -ForegroundColor Cyan

$VENV = Join-Path $API ".venv"
$PY = Join-Path $VENV "Scripts\python.exe"

if (-not (Test-Path $VENV)) {

    Write-Host "Creating backend virtualenv..."

    Push-Location $API

    try {
        python -m venv .venv

        if ($LASTEXITCODE -ne 0) {
            throw "Python virtualenv creation failed"
        }

        & $PY -m pip install --quiet -r requirements.txt -r requirements-dev.txt

        if ($LASTEXITCODE -ne 0) {
            throw "Backend dependency installation failed"
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host ".venv present - skipping pip install"
}

# ------------------------------------------------------------
# 3. Reset
# ------------------------------------------------------------

if ($RESET) {

    Write-Host ""
    Write-Host "== SAFE DEMO RESET ==" -ForegroundColor Cyan

    & (Join-Path $PSScriptRoot "reset-demo.ps1")

    if ($LASTEXITCODE -ne 0) {
        throw "Demo reset failed"
    }
}

# ------------------------------------------------------------
# 4. Fresh database
# ------------------------------------------------------------

if ($FRESH) {

    Write-Host ""
    Write-Host "== FRESH DATABASE ==" -ForegroundColor Cyan

    $DB = Join-Path $API "legalmet.db"
    $STORAGE = Join-Path $API "storage"

    if (Test-Path $DB) {
        Remove-Item $DB -Force
        Write-Host "Removed legalmet.db"
    }

    if (Test-Path $STORAGE) {
        Remove-Item $STORAGE -Recurse -Force
        Write-Host "Removed storage/"
    }

    Write-Host "Fresh database will be initialized by the backend."
}

# ------------------------------------------------------------
# 5. Start backend
# ------------------------------------------------------------

Write-Host ""
Write-Host "== Starting backend ==" -ForegroundColor Cyan

$backend = Start-Process `
    -FilePath $PY `
    -ArgumentList "-m","uvicorn","app.main:app","--port","8000" `
    -WorkingDirectory $API `
    -PassThru

# ------------------------------------------------------------
# 6. Start frontend
# ------------------------------------------------------------

Write-Host ""
Write-Host "== Starting frontend ==" -ForegroundColor Cyan

$frontend = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList "run","dev:web" `
    -WorkingDirectory $ROOT `
    -PassThru

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " METRASIGHT LOCAL DEMO RUNNING" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend : $FRONTEND_URL"
Write-Host "Backend  : $BACKEND_URL/api/v1/health"
Write-Host ""
Write-Host "Inspector login:"
Write-Host "inspector@legalmet.local"
Write-Host "changeme-inspector"
Write-Host ""
Write-Host "Press Ctrl+C to stop the demo."
Write-Host ""

try {

    while ($true) {

        if ($backend.HasExited) {
            Write-Host "Backend stopped." -ForegroundColor Red
            break
        }

        if ($frontend.HasExited) {
            Write-Host "Frontend stopped." -ForegroundColor Red
            break
        }

        Start-Sleep -Seconds 2
    }

}
finally {

    Write-Host ""
    Write-Host "== Stopping METRASIGHT ==" -ForegroundColor Yellow

    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }

    if (-not $frontend.HasExited) {
        Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    }

    Write-Host "Servers stopped."
}
