<#
Test whether scheduled tasks can drive UI in the user's interactive Session 1
when invoked from SSH (Session 0).
#>
$ErrorActionPreference = "Continue"

# The action: pop a MessageBox in Session 1
# Use a separate inner script file to avoid quote escaping hell
$innerScript = @'
Add-Type -AssemblyName System.Windows.Forms
$result = [System.Windows.Forms.MessageBox]::Show(
    "PHASE 12 PROBE: Scheduled-task workaround is WORKING. SSH (Session 0) successfully launched UI in your Session 1. Click OK to dismiss.",
    "Session 1 SSH-driven UI test",
    "OK",
    "Information"
)
"task fired at $(Get-Date -Format o)" | Set-Content -LiteralPath "$env:USERPROFILE\tc_phase12_session_test.log" -Force
'@
$innerScriptPath = "$env:USERPROFILE\tc_phase12_session_test_inner.ps1"
$innerScript | Set-Content -LiteralPath $innerScriptPath -Force

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$innerScriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddSeconds(8))
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -DeleteExpiredTaskAfter (New-TimeSpan -Seconds 60) -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings

Register-ScheduledTask -TaskName "tc_phase12_session_test" -InputObject $task -Force | Out-Null
Write-Host "Scheduled task registered."
Write-Host "Trigger time: $((Get-Date).AddSeconds(8).ToString('HH:mm:ss'))"
Write-Host "Inner script: $innerScriptPath"
Write-Host "If you see a popup on your VM desktop in ~8s, the workaround works."
Write-Host "Click OK to dismiss; the task will write a log file at $env:USERPROFILE\tc_phase12_session_test.log"
