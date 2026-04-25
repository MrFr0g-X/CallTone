# tunnel-watchdog.ps1
# Keeps the SSH tunnel localhost:8090 -> vast:8081 alive. Restarts ssh
# whenever it dies (sleep, network blip, server kick). Designed to be
# launched as a Windows Scheduled Task at logon so the tunnel is always up.
#
# Logs to %USERPROFILE%\.calltone-tunnel.log (rotated by exit).

$ErrorActionPreference = "Stop"

$RemoteHost   = "185.65.93.114"
$RemotePort   = 44049
$LocalPort    = 8090
$RemoteTarget = 8081
$LogPath      = Join-Path $env:USERPROFILE ".calltone-tunnel.log"

function Log($msg) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "$stamp $msg" | Out-File -FilePath $LogPath -Append -Encoding utf8
}

# Self-heal: if a stale ssh on the same port exists, kill it first.
$stale = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
foreach ($c in $stale) {
    try {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
        Log "killed stale listener PID $($c.OwningProcess) on :$LocalPort"
    } catch {}
}

Log "watchdog start: $LocalPort -> $RemoteHost`:$RemotePort -> :$RemoteTarget"

# Start-Process refuses to share one file across stdout+stderr (sharing
# violation), so we write to two and tail-merge into the main log on exit.
$SshOutLog = Join-Path $env:USERPROFILE ".calltone-tunnel.ssh.out.log"
$SshErrLog = Join-Path $env:USERPROFILE ".calltone-tunnel.ssh.err.log"
$delay = 3
while ($true) {
    $start = Get-Date
    $sshArgs = @(
        "-o","ExitOnForwardFailure=yes",
        "-o","ServerAliveInterval=15",
        "-o","ServerAliveCountMax=2",
        "-o","TCPKeepAlive=yes",
        "-o","ConnectTimeout=10",
        "-o","StrictHostKeyChecking=accept-new",
        "-o","BatchMode=yes",
        "-N","-L","$LocalPort`:localhost:$RemoteTarget",
        "-p","$RemotePort","root@$RemoteHost"
    )
    # Start-Process is the only sane way to run native exes from PowerShell:
    # the call operator (&) turns stderr lines into ErrorRecord objects, which
    # makes ssh's "Welcome to vast.ai" banner look like a fatal exception.
    $p = Start-Process -FilePath ssh -ArgumentList $sshArgs `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput $SshOutLog `
            -RedirectStandardError  $SshErrLog
    Log "ssh launched PID $($p.Id)"
    $p.WaitForExit()
    $elapsed = [int]((Get-Date) - $start).TotalSeconds
    # Bubble up ssh's last few lines so we can diagnose without opening a 2nd file.
    $tail = @()
    foreach ($f in @($SshErrLog, $SshOutLog)) {
        if (Test-Path $f) { $tail += (Get-Content $f -Tail 3 -ErrorAction SilentlyContinue) }
    }
    foreach ($line in $tail) { if ($line) { Log "ssh> $line" } }
    if ($elapsed -lt 5) {
        # Failed fast (auth, network down) -> back off harder.
        $delay = [Math]::Min($delay * 2, 60)
    } else {
        # Stayed up a while -> reset to fast retry on next death.
        $delay = 3
    }
    Log "ssh PID $($p.Id) exited code=$($p.ExitCode) after ${elapsed}s; sleeping ${delay}s"
    Start-Sleep -Seconds $delay
}
