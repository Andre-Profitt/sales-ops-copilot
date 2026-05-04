<#
SSH-triggered wrapper: copies AISidePane test to local, registers in Session 1.
#>
$ErrorActionPreference = "Continue"

Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\probe_aisidepane_executemso.ps1" `
    -Destination "$env:USERPROFILE\tc_ai_probe.ps1" -Force
Write-Host "Copied: $env:USERPROFILE\tc_ai_probe.ps1 ($((Get-Item $env:USERPROFILE\tc_ai_probe.ps1).Length) bytes)"

Remove-Item "$env:USERPROFILE\tc_aisidepane_test.json" -Force -ErrorAction SilentlyContinue

$tn = "tc_ai_probe_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_ai_probe.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")

& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered task: $tn"
