$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$sgBinary = Join-Path (Split-Path -Parent $PSScriptRoot) 'tools\cloudflared.exe'
if (Test-Path -LiteralPath 'tunnel.pid') {
    $sgTargetId = [int](Get-Content -LiteralPath 'tunnel.pid')
    $sgTarget = Get-Process -Id $sgTargetId -ErrorAction SilentlyContinue
    if ($sgTarget -and $sgTarget.Path -eq $sgBinary) {
        Stop-Process -Id $sgTargetId
        Write-Output 'SteamGamers tunnel stopped. Telegram bot was left running.'
    } else { Write-Output 'SteamGamers tunnel is not running.' }
}
