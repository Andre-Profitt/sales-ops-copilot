<# Write a wrapper .bat then schedule it. Avoids schtasks /tr quoting hell. #>
$ErrorActionPreference = "Continue"

# Stage capture script if missing
if (-not (Test-Path "C:\Users\test\tc_aicore.ps1")) {
    Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\capture_aicore_oneshot.ps1" `
        -Destination "C:\Users\test\tc_aicore.ps1" -Force
}

# Wrapper batch that launches a visible PowerShell window
$bat = "C:\Users\test\tc_capture_launcher.bat"
@'
@echo off
start "AI Core Capture" powershell.exe -NoExit -ExecutionPolicy Bypass -File C:\Users\test\tc_aicore.ps1 -DurationSeconds 180
'@ | Set-Content -LiteralPath $bat -Encoding ASCII -Force

# Schedule the .bat in Session 1
$tn = "tc_capture_$(Get-Date -Format yyyyMMddHHmmss)"
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $bat /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Output "Launched: $tn"
Write-Output ""
Write-Output "WHAT TO DO:"
Write-Output "  1. A PowerShell window should appear on your VM desktop in a few seconds."
Write-Output "  2. Wait ~10s for the YELLOW 'ACTION REQUIRED' banner to show."
Write-Output "  3. Open PowerPoint (the script kills any running PP first)."
Write-Output "  4. Click think-cell tab -> AI Side Pane button (Elements group)."
Write-Output "  5. Type a prompt (e.g. 'show me revenue 100 200 300') -> Enter."
Write-Output "  6. Wait for AI response."
Write-Output "  7. Countdown ends after 180s. Capture path printed in the window."
