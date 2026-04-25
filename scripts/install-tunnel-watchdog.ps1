# install-tunnel-watchdog.ps1
# Registers a per-user Scheduled Task that runs tunnel-watchdog.ps1 at logon
# (and restarts it on failure). No admin required.
#
# Re-run safe -- replaces the existing task if present.

$ErrorActionPreference = "Stop"

$TaskName  = "CallTone-SSH-Tunnel"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Watchdog  = Join-Path $ScriptDir "tunnel-watchdog.ps1"

if (-not (Test-Path $Watchdog)) {
    throw "watchdog script not found at $Watchdog"
}

$Action  = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Watchdog`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
# Keep the watchdog itself resilient: restart on any failure, no time limit.
$Settings = New-ScheduledTaskSettingsSet `
              -RestartCount 999 `
              -RestartInterval (New-TimeSpan -Minutes 1) `
              -ExecutionTimeLimit ([TimeSpan]::Zero) `
              -StartWhenAvailable `
              -DontStopIfGoingOnBatteries `
              -AllowStartIfOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

# Replace if exists.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed existing task '$TaskName'"
}

Register-ScheduledTask -TaskName $TaskName `
    -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal `
    -Description "Maintains SSH tunnel localhost:8090 -> Vast :8081 for CallTone model server" | Out-Null

Write-Host "registered scheduled task '$TaskName' (runs at every logon)"
Write-Host "starting it now..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 4

# Probe.
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8090/v1/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "tunnel reachable, model server says: $($r.Content)"
} catch {
    Write-Host "tunnel not yet up -- check log at $env:USERPROFILE\.calltone-tunnel.log"
}
