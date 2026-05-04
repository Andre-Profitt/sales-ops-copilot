<# Launch v3 capture in a visible Session 1 PowerShell window. #>
$ErrorActionPreference = "Continue"

# Stage v3 script
Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\capture_aicore_v3_no_http3.ps1" `
    -Destination "C:\Users\test\tc_capture_v3.ps1" -Force

# Write a wrapper batch
$bat = "C:\Users\test\tc_v3_launcher.bat"
@'
@echo off
start "AI Core Capture v3 (no QUIC)" powershell.exe -NoExit -ExecutionPolicy Bypass -File C:\Users\test\tc_capture_v3.ps1 -DurationSeconds 300
'@ | Set-Content -LiteralPath $bat -Encoding ASCII -Force

# Schedule in Session 1
$tn = "tc_v3_$(Get-Date -Format yyyyMMddHHmmss)"
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $bat /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Output "Triggered: $tn"
