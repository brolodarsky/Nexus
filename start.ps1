<#
.SYNOPSIS
    Launches the Nexus Engine Control Panel (backend + frontend).
.DESCRIPTION
    Starts the FastAPI backend in a background job and the Next.js
    dev server in the foreground. Press Ctrl+C to stop the frontend;
    the backend job is cleaned up automatically on exit.
#>

$PROJECT_ROOT = $PSScriptRoot
$VENV_PYTHON  = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"
$ENGINE_DIR   = Join-Path $PROJECT_ROOT "engine"
$GUI_DIR      = Join-Path $PROJECT_ROOT "gui"

Write-Host ""
Write-Host "  ═══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host "  ║         🧠 Nexus Control Panel              ║" -ForegroundColor Cyan
Write-Host "  ═══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""

# ── Start FastAPI backend ────────────────────────────────────
Write-Host "  [1/2] Starting FastAPI backend on port 8000..." -ForegroundColor Yellow
$backend = Start-Process -FilePath $VENV_PYTHON `
    -ArgumentList "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory $ENGINE_DIR `
    -WindowStyle Hidden `
    -PassThru

Start-Sleep -Seconds 2

# Quick health check
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5
    Write-Host "  [✓] Backend online: $($health.engine) v$($health.version)" -ForegroundColor Green
} catch {
    Write-Host "  [!] Backend may still be starting..." -ForegroundColor DarkYellow
}

# ── Start Next.js frontend ──────────────────────────────────
Write-Host "  [2/2] Starting Next.js frontend on port 3000..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  → Open http://localhost:3000" -ForegroundColor Cyan
Write-Host "  → Press Ctrl+C to shut down" -ForegroundColor DarkGray
Write-Host ""

try {
    Set-Location $GUI_DIR
    npm run dev
} finally {
    # Clean up backend when frontend exits
    if ($backend -and !$backend.HasExited) {
        Write-Host ""
        Write-Host "  Shutting down backend (PID $($backend.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  👋 Nexus Control Panel stopped." -ForegroundColor DarkGray
    Set-Location $PROJECT_ROOT
}
