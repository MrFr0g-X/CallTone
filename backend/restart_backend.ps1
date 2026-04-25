# Kill any backend on :8000 and restart from a fresh process so the
# new main.py is loaded. Inherits MODEL_SERVER_* from .env.demo.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$envDemo = Join-Path $root ".env.demo"
$backendDir = $PSScriptRoot

# 1) Kill anything on :8000
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $existing) {
    $pidToKill = $c.OwningProcess
    Write-Host "Stopping PID $pidToKill on :8000"
    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 2) Source .env.demo
if (Test-Path $envDemo) {
    Get-Content $envDemo | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $k = $matches[1].Trim()
            $v = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($k, $v, "Process")
            Write-Host "  env $k set"
        }
    }
}

# 3) Launch backend in detached window so it survives this script's shell
$python = "C:\Users\Hothifa Hamdan\AppData\Local\Programs\Python\Python310\python.exe"
$args = @("-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--reload")
Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $backendDir -WindowStyle Hidden
Start-Sleep -Seconds 2
$proc = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddSeconds(-5) }
$proc | Select-Object Id, StartTime | Format-Table -AutoSize
Write-Host "Backend restart launched. Wait ~5s then probe http://localhost:8000/api/health"
