<#
SSH-triggered wrapper: copies + schedules the AI-click capture in Session 1.
#>
$ErrorActionPreference = "Continue"

$srcUnc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\run_phase12_with_ai_click.ps1"
$localCopy = "$env:USERPROFILE\tc_phase12_with_click.ps1"

Copy-Item -LiteralPath $srcUnc -Destination $localCopy -Force
Write-Host "Local: $localCopy ($((Get-Item $localCopy).Length) bytes)"

Remove-Item "$env:USERPROFILE\tc_phase12_capture_done.json" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\tc_phase12_capture_started.json" -Force -ErrorAction SilentlyContinue

$tn = "tc_phase12_click_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$localCopy`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")

& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
Write-Host "Marker: $env:USERPROFILE\tc_phase12_capture_done.json"
