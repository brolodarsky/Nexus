<#
.SYNOPSIS
    Launches the Nexus Engine Control Panel (backend + frontend).
.DESCRIPTION
    Starts the FastAPI backend in a background job and the Next.js
    dev server in the foreground. Binds both to 0.0.0.0 so the Control
    Panel is accessible on localhost and across LAN/Tailscale on mobile.
    Press Ctrl+C to stop the frontend; the backend job is cleaned up
    automatically on exit.
#>

$PROJECT_ROOT = $PSScriptRoot
$VENV_PYTHON  = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"
$GUI_DIR      = Join-Path $PROJECT_ROOT "gui"

Write-Host ""
Write-Host "  ═══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host "  ║         🧠 Nexus Control Panel              ║" -ForegroundColor Cyan
Write-Host "  ═══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""

# ── Start FastAPI backend ────────────────────────────────────
Write-Host "  [1/2] Starting FastAPI backend on port 8000..." -ForegroundColor Yellow

# Free port 8000 if an orphaned Uvicorn worker from a prior session is still bound to it
$staleConn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($staleConn -and $staleConn.OwningProcess) {
    Write-Host "  [!] Port 8000 is occupied by stale PID $($staleConn.OwningProcess). Terminating..." -ForegroundColor DarkYellow
    taskkill /T /F /PID $staleConn.OwningProcess 2>$null | Out-Null
    Start-Sleep -Seconds 1
}

# Ensure logs directory exists for background Uvicorn stdout/stderr capture
$LOGS_DIR = Join-Path $PROJECT_ROOT "logs"
if (-not (Test-Path $LOGS_DIR)) {
    New-Item -ItemType Directory -Path $LOGS_DIR -Force | Out-Null
}
$uvicornLog = Join-Path $LOGS_DIR "uvicorn.log"
$uvicornErr = Join-Path $LOGS_DIR "uvicorn_err.log"

# ArgumentList escaping directive:
# We pass -ArgumentList as a single escaped string with literal quotes (`\"*.db*\"` and `\"*.sqlite*\"`).
# In Windows, passing wildcards as unquoted arguments to Python causes the C runtime (MSVCRT setargv)
# to automatically expand wildcards against matching files in the working directory (e.g. chats.db, hitl.db),
# producing unexpected positional arguments that crash Uvicorn/Click on startup. Quoting suppresses expansion.
# --host 0.0.0.0: Binds the HTTP listener to all IPv4 network interfaces (loopback, local Wi-Fi/Ethernet, and Tailscale VPN),
# allowing remote clients (e.g. mobile phones on LAN or Tailscale) to connect directly to the backend.
# --port 8000: Default HTTP port for the FastAPI engine.
# --reload: Automatically reloads the worker process when Python source files change.
# --reload-dir: Scopes file watching strictly to `src/nexus` (ignoring tests/, scripts/, gui/, and Vault/).
# --reload-exclude: Prevents standalone CLI scripts (e.g. export_conversation.py) and SQLite WAL/DB files from killing in-flight chat turns.
# --timeout-graceful-shutdown: Gives active SSE streams up to 30s to finish before terminating the worker.
# -RedirectStandardOutput / -RedirectStandardError: Captures Uvicorn startup traces and error stacks to disk for inspection.
$backendArgs = '-m uvicorn nexus.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir src/nexus --reload-exclude \"*.db*\" --reload-exclude \"*.sqlite*\" --reload-exclude export_conversation.py --timeout-graceful-shutdown 30'
$backend = Start-Process -FilePath $VENV_PYTHON `
    -ArgumentList $backendArgs `
    -WorkingDirectory $PROJECT_ROOT `
    -WindowStyle Hidden `
    -RedirectStandardOutput $uvicornLog `
    -RedirectStandardError $uvicornErr `
    -PassThru

# Polling health check with process exit detection
# Python and Uvicorn import heavy packages (FastAPI, LangGraph, Pydantic, Chroma) during startup,
# which typically takes 3-6 seconds. We poll /api/health every second up to 15 seconds.
$backendReady = $false
$maxRetries = 15
for ($i = 1; $i -le $maxRetries; $i++) {
    if ($backend.HasExited) {
        Write-Host "  [✗] Backend process exited unexpectedly with code $($backend.ExitCode)!" -ForegroundColor Red
        if (Test-Path $uvicornErr) {
            Write-Host "  ─── Backend Error Output (tail) ───" -ForegroundColor Red
            Get-Content $uvicornErr -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkRed }
            Write-Host "  ───────────────────────────────────" -ForegroundColor Red
        }
        break
    }
    try {
        # -TimeoutSec 1: Fast probe; fails immediately if port 8000 is not yet accepting connections
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 1 -ErrorAction Stop
        Write-Host "  [✓] Backend online: $($health.engine) v$($health.version) (ready in ${i}s)" -ForegroundColor Green
        # Display Telegram Mobile Bridge long-poller status returned by /api/health
        if ($health.telegram) {
            if ($health.telegram.configured -and $health.telegram.enabled) {
                $botLabel = if ($health.telegram.bot_username) { "@$($health.telegram.bot_username)" } else { "polling" }
                Write-Host "  [✓] Telegram Mobile Bridge: Active ($botLabel)" -ForegroundColor Green
            } elseif (-not $health.telegram.configured) {
                Write-Host "  [i] Telegram Mobile Bridge: Standby (set TELEGRAM_BOT_TOKEN in .env to enable)" -ForegroundColor DarkGray
            }
        }
        $backendReady = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $backendReady -and -not $backend.HasExited) {
    Write-Host "  [!] Backend did not respond within ${maxRetries}s (may still be initializing)..." -ForegroundColor DarkYellow
}

# ── Network IP Discovery (LAN & Tailscale) ─────────────────────
# Dynamically inspect network interfaces to display exact mobile URLs in the terminal banner
$tailscaleIp = $null
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    try {
        $tsOutput = (tailscale ip -4 2>$null)
        if ($tsOutput) {
            $tailscaleIp = $tsOutput.Trim()
        }
    } catch {
        $tailscaleIp = $null
    }
}
if (-not $tailscaleIp) {
    # Check for Tailscale CGNAT IP range (100.64.0.0/10) via NetIPAddress if tailscale CLI is not on PATH
    $tsAdapter = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like "100.*" } | Select-Object -First 1
    if ($tsAdapter) {
        $tailscaleIp = $tsAdapter.IPAddress
    }
}

$lanIp = $null
# Query private IPv4 network adapters (excluding loopback 127.x, link-local 169.254.x, and Tailscale 100.x)
$lanAdapter = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
    $_.IPAddress -notlike "127.*" -and
    $_.IPAddress -notlike "169.254.*" -and
    $_.IPAddress -notlike "100.*"
} | Select-Object -First 1
if ($lanAdapter) {
    $lanIp = $lanAdapter.IPAddress
}

# ── Start Next.js frontend ──────────────────────────────────
Write-Host "  [2/2] Starting Next.js frontend on port 3000..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  → Local:     http://localhost:3000" -ForegroundColor Cyan
if ($tailscaleIp) {
    Write-Host "  → Tailscale: http://${tailscaleIp}:3000" -ForegroundColor Green
}
if ($lanIp) {
    Write-Host "  → LAN:       http://${lanIp}:3000" -ForegroundColor DarkCyan
}
Write-Host "  → Press Ctrl+C to shut down" -ForegroundColor DarkGray
Write-Host ""

try {
    Set-Location $GUI_DIR
    # -H 0.0.0.0: Binds the Next.js dev server to all network interfaces so mobile browsers over LAN or Tailscale can connect
    # -p 3000: Specifies the frontend HTTP port
    npx next dev -H 0.0.0.0 -p 3000
} finally {
    # Clean up backend when frontend exits
    # NOTE: taskkill /T kills the entire process tree. This is critical
    # because uvicorn --reload spawns child workers that survive if only
    # the parent PID is killed, leaving zombie processes on port 8000.
    if ($backend -and !$backend.HasExited) {
        Write-Host ""
        Write-Host "  Shutting down backend (PID $($backend.Id))..." -ForegroundColor Yellow
        taskkill /T /F /PID $backend.Id 2>$null | Out-Null
    }
    Write-Host "  👋 Nexus Control Panel stopped." -ForegroundColor DarkGray
    Set-Location $PROJECT_ROOT
}
