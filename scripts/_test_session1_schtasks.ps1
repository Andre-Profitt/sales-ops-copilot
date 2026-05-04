<#
Use schtasks.exe (legacy) — more reliable than New-ScheduledTask cmdlets
for one-shot Interactive tasks.

Test if scheduled-task in Session 1 can show UI when triggered from SSH.
#>
$ErrorActionPreference = "Continue"

# Inner script — separate file to avoid quote escaping
$innerScript = @'
"task fired at $(Get-Date -Format o), interactive=$([System.Environment]::UserInteractive), session=$((Get-Process -PID $PID).SessionId)" | Set-Content -LiteralPath "$env:USERPROFILE\tc_session_test.log" -Force
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show("PHASE 12: scheduled task ran in your Session 1. Click OK to dismiss.", "tc Session 1 test", "OK", "Information") | Out-Null
"dismissed at $(Get-Date -Format o)" | Add-Content -LiteralPath "$env:USERPROFILE\tc_session_test.log"
'@
$innerPath = "$env:USERPROFILE\tc_session_test_inner.ps1"
$innerScript | Set-Content -LiteralPath $innerPath -Force
Write-Host "Inner script written to $innerPath"

# Trigger 5 seconds from now (HH:mm format for schtasks)
$triggerTime = (Get-Date).AddSeconds(10).ToString("HH:mm")
$taskName = "tc_session_test_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$innerPath`""

# /sc once — single run
# /st HH:mm — start time
# /tr — task to run
# /it — interactive (runs only when user is logged on, in their session)
# /f — force overwrite
# /rl limited — non-elevated (admin not needed)
$arg = @(
    "/create",
    "/sc", "once",
    "/st", $triggerTime,
    "/tn", $taskName,
    "/tr", "`"$cmd`"",
    "/it",
    "/rl", "limited",
    "/f"
)
$out = & schtasks.exe @arg 2>&1
Write-Host "schtasks output:"
Write-Host ($out -join "`n")
Write-Host ""
Write-Host "Task name: $taskName"
Write-Host "Trigger: $triggerTime"
Write-Host "Wait ~12s then check $env:USERPROFILE\tc_session_test.log for evidence"

# Optionally: also Run the task IMMEDIATELY (rather than waiting for the trigger)
Start-Sleep -Seconds 1
& schtasks.exe /run /tn $taskName 2>&1 | Out-Null
Write-Host "Task /run requested (in addition to scheduled trigger)."
