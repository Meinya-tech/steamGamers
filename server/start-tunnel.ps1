param([ValidateSet('auto','http2','quic')][string]$Protocol='auto')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$sgRoot = Split-Path -Parent $PSScriptRoot
$sgBinary = Join-Path $sgRoot 'tools\cloudflared.exe'
if (-not (Test-Path -LiteralPath $sgBinary)) { throw 'cloudflared.exe is missing from tools.' }
if (Test-Path -LiteralPath 'tunnel.pid') {
    $sgOldId = [int](Get-Content -LiteralPath 'tunnel.pid')
    $sgOld = Get-Process -Id $sgOldId -ErrorAction SilentlyContinue
    if ($sgOld -and $sgOld.Path -eq $sgBinary) {
        Write-Output 'Tunnel is already running.'
        if (Test-Path -LiteralPath 'tunnel-url.txt') { Get-Content -LiteralPath 'tunnel-url.txt' }
        exit
    }
}
if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 8082 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    $sgPython = (Get-Command python).Source
    $sgGateway = Start-Process -FilePath $sgPython -ArgumentList 'public_gateway.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'gateway-output.log') -RedirectStandardError (Join-Path $PSScriptRoot 'gateway-error.log') -PassThru
    $sgGateway.Id | Set-Content -LiteralPath 'gateway.pid'
}
$sgTunnel = Start-Process -FilePath $sgBinary -ArgumentList @('tunnel','--no-autoupdate','--protocol',$Protocol,'--edge-ip-version','4','--url','http://127.0.0.1:8082') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'tunnel-output.log') -RedirectStandardError (Join-Path $PSScriptRoot 'tunnel-error.log') -PassThru
$sgTunnel.Id | Set-Content -LiteralPath 'tunnel.pid'
for ($sgAttempt=0; $sgAttempt -lt 30; $sgAttempt++) {
    Start-Sleep -Seconds 1
    $sgLog = Get-Content -LiteralPath 'tunnel-error.log' -Raw -ErrorAction SilentlyContinue
    $sgMatch = [regex]::Match([string]$sgLog,'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($sgMatch.Success -and $sgLog.Contains('Registered tunnel connection')) {
        $sgMatch.Value | Set-Content -LiteralPath 'tunnel-url.txt'
        Write-Output ('Temporary URL: '+$sgMatch.Value)
        Write-Output 'After restarting the tunnel, update the site endpoint. Keep this PC awake.'
        exit
    }
    if ($sgTunnel.HasExited) { throw 'Tunnel exited. Check tunnel-error.log.' }
}
Write-Output 'Tunnel connection is not verified. A generated URL alone does not mean it is working; check tunnel-error.log.'
