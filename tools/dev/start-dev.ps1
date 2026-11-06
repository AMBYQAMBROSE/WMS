# Starts the local development environment: SQL Server container, backend API and web dev server.
# Run it through start-dev.bat in the repository root (double-click). Safe to rerun: anything
# already running is left alone.
#
# First run also creates the backend venv, copies .env.example to .env, installs dependencies and
# seeds base data. The administrator is created as admin / $env:SEED_ADMIN_PASSWORD (default Admin@123).

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$backend = Join-Path $root 'apps\backend'
$web = Join-Path $root 'apps\web'
$compose = Join-Path $root 'infra\docker'
$saPassword = 'YourPassword123!'   # matches infra/docker/docker-compose.yml
$sqlcmd = '/opt/mssql-tools18/bin/sqlcmd'

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Invoke-Native {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

function Test-Port($port) {
    [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

# `docker info` can hang while the engine is half up, so run it with a timeout.
function Test-Docker {
    $p = Start-Process docker -ArgumentList 'info' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$env:TEMP\wms-docker-info.out" -RedirectStandardError "$env:TEMP\wms-docker-info.err"
    $null = $p.Handle
    if (-not $p.WaitForExit(15000)) { $p.Kill(); return $false }
    $p.ExitCode -eq 0
}

function Wait-Docker($seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Docker) { return $true }
        Start-Sleep 3
    }
    $false
}

function Start-DockerDesktop {
    $exe = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) { throw 'Docker Desktop not found. Install it or start it manually.' }
    Start-Process $exe
}

function Wait-Http($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 5 | Out-Null; return $true } catch { Start-Sleep 1 }
    }
    $false
}

# Opens a new console window running $command in $dir; closing the window stops the server.
function Start-Window($title, $dir, $command) {
    $cmd = "`$host.UI.RawUI.WindowTitle = '$title'; Set-Location '$dir'; $command"
    Start-Process powershell -ArgumentList '-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $cmd
}

# --- 1. Docker ------------------------------------------------------------------------------
Step 'Checking Docker'
if (-not (Test-Docker)) {
    if (-not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
        Write-Host '    Starting Docker Desktop...'
        Start-DockerDesktop
    }
    Write-Host '    Waiting for the Docker engine (up to 3 minutes)...'
    if (-not (Wait-Docker 180)) {
        # Seen on this machine: Docker Desktop runs but its WSL VM never comes up. Restarting WSL fixes
        # it, but `wsl --shutdown` stops every distro, so only do it when Docker's is the only one.
        $distros = @((wsl -l -q) -replace "`0", '' | Where-Object { $_.Trim() })
        if ($distros.Count -eq 1 -and $distros[0].Trim() -eq 'docker-desktop') {
            Write-Host '    Engine not responding; restarting Docker Desktop and WSL...'
            Get-Process 'Docker Desktop', 'com.docker.backend', 'com.docker.build' -ErrorAction SilentlyContinue |
                Stop-Process -Force
            wsl --shutdown
            Start-Sleep 3
            Start-DockerDesktop
            if (-not (Wait-Docker 180)) { throw 'Docker engine still not responding. Restart Docker Desktop manually.' }
        } else {
            throw "Docker engine not responding. Quit Docker Desktop, run 'wsl --shutdown', start it again, then rerun this script."
        }
    }
}

# --- 2. Database ----------------------------------------------------------------------------
Step 'Starting SQL Server container'
Push-Location $compose
try { Invoke-Native 'docker compose up' { docker compose up -d db } } finally { Pop-Location }
$container = (docker compose -f (Join-Path $compose 'docker-compose.yml') ps -q db).Trim()

Write-Host '    Waiting for SQL Server...'
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    # Redirected stderr becomes a terminating error under 'Stop' in Windows PowerShell 5.1.
    try { docker exec $container $sqlcmd -S localhost -U sa -P $saPassword -C -Q 'SELECT 1' *> $null } catch {}
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep 2
}
if (-not $ready) { throw 'SQL Server did not become ready within 2 minutes' }
Invoke-Native 'Create database' {
    docker exec $container $sqlcmd -S localhost -U sa -P $saPassword -C -Q "IF DB_ID('wms') IS NULL CREATE DATABASE wms" | Out-Null
}

# --- 3. Backend -----------------------------------------------------------------------------
Step 'Preparing backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host '    Creating virtual environment...'
    Invoke-Native 'Create venv' { py -3.15 -m venv (Join-Path $backend '.venv') }
}
# Reinstall dependencies only when requirements.txt changed since the last install.
$reqs = Join-Path $backend 'requirements.txt'
$stamp = Join-Path $backend '.venv\.requirements-installed'
if (-not (Test-Path $stamp) -or (Get-Item $reqs).LastWriteTime -gt (Get-Item $stamp).LastWriteTime) {
    Write-Host '    Installing Python dependencies...'
    Invoke-Native 'pip install' { & $python -m pip install --prefer-binary -q -r $reqs }
    New-Item -ItemType File -Force $stamp | Out-Null
}
$envFile = Join-Path $backend '.env'
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $backend '.env.example') $envFile }

Push-Location $backend
try {
    Write-Host '    Applying migrations...'
    Invoke-Native 'alembic upgrade' { & $python -m alembic upgrade head }
    # The password is only used when the administrator does not exist yet.
    if (-not $env:SEED_ADMIN_PASSWORD) { $env:SEED_ADMIN_PASSWORD = 'Admin@123' }
    Invoke-Native 'Seed' { & $python -m scripts.seed }
} finally { Pop-Location }

if (Test-Port 8000) {
    Write-Host '    Port 8000 already in use; assuming the backend is running.'
} else {
    Start-Window 'WMS backend :8000' $backend "& '$python' -m uvicorn app.main:app --port 8000"
}

# --- 4. Web ---------------------------------------------------------------------------------
Step 'Preparing web'
$lock = Join-Path $web 'package-lock.json'
$installed = Join-Path $web 'node_modules\.package-lock.json'
if (-not (Test-Path $installed) -or (Get-Item $lock).LastWriteTime -gt (Get-Item $installed).LastWriteTime) {
    Write-Host '    Installing npm dependencies...'
    Push-Location $web
    try { Invoke-Native 'npm install' { npm install --no-audit --no-fund } } finally { Pop-Location }
}
if (Test-Port 5173) {
    Write-Host '    Port 5173 already in use; assuming the web dev server is running.'
} else {
    Start-Window 'WMS web :5173' $web 'npm run dev'
}

# --- 5. Open the browser --------------------------------------------------------------------
Step 'Waiting for servers'
if (-not (Wait-Http 'http://localhost:8000/docs' 90)) { throw 'Backend did not respond on port 8000; check the "WMS backend" window' }
if (-not (Wait-Http 'http://localhost:5173/' 90)) { throw 'Web dev server did not respond on port 5173; check the "WMS web" window' }
Start-Process 'http://localhost:5173'

Write-Host ''
Write-Host 'WMS is running.' -ForegroundColor Green
Write-Host '  Web console: http://localhost:5173'
Write-Host '  API docs:    http://localhost:8000/docs'
Write-Host '  Close the "WMS backend" / "WMS web" windows to stop the servers.'
