<# Launch a visible PowerShell window in Session 1 that runs the capture. #>
$ErrorActionPreference = "Continue"

# Stage the capture script if missing
if (-not (Test-Path "C:\Users\test\tc_aicore.ps1")) {
    Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\capture_aicore_oneshot.ps1" `
        -Destination "C:\Users\test\tc_aicore.ps1" -Force
}

# Schedule a PowerShell window that runs the capture script
# /it = interactive (uses console session)
# /rl limited = non-elevated (UAC won't fire)
# Use cmd.exe /c start "..." powershell.exe so we get a NEW visible window
$tn = "tc_capture_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "cmd.exe /c start `"AI Core Capture`" powershell.exe -NoExit -ExecutionPolicy Bypass -File C:\Users\test\tc_aicore.ps1 -DurationSeconds 180"
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Output "Launched: $tn"
Write-Output "A PowerShell window should appear on your VM desktop momentarily."
Write-Output "It will run the capture script for 180s."
