<#
SSH-triggered wrapper: copies run_phase12_noclick_capture.ps1 to a local
VM path, registers a one-shot scheduled task that runs it in Session 1,
fires the task, returns the task name.

The polling loop on the SSH side then watches for the completion marker.
#>
$ErrorActionPreference = "Continue"

$srcUnc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\run_phase12_noclick_capture.ps1"
$localCopy = "$env:USERPROFILE\tc_phase12_capture.ps1"

Write-Host "Copying capture script: $srcUnc -> $localCopy"
Copy-Item -LiteralPath $srcUnc -Destination $localCopy -Force
if (-not (Test-Path -LiteralPath $localCopy)) {
    Write-Host "FAILED: could not copy script. Aborting."
    exit 2
}
$sz = (Get-Item -LiteralPath $localCopy).Length
Write-Host "Local copy size: $sz bytes"

# Clean any stale markers from a previous run
Remove-Item -LiteralPath "$env:USERPROFILE\tc_phase12_capture_done.json" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$env:USERPROFILE\tc_phase12_capture_started.json" -Force -ErrorAction SilentlyContinue

# Register one-shot scheduled task to run the capture in Session 1
$taskName = "tc_phase12_run_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$localCopy`""

# /st must be HH:mm — fire at "now+1min" and also issue /run for immediate
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")

$schtasksArgs = @(
    "/create",
    "/sc", "once",
    "/st", $st,
    "/tn", $taskName,
    "/tr", $cmd,
    "/it",
    "/rl", "limited",
    "/f"
)
$createOut = & schtasks.exe @schtasksArgs 2>&1
Write-Host "schtasks /create output:"
Write-Host ($createOut -join "`n")

$runOut = & schtasks.exe /run /tn $taskName 2>&1
Write-Host "schtasks /run output:"
Write-Host ($runOut -join "`n")

Write-Host ""
Write-Host "Task name: $taskName"
Write-Host "Trigger: $st (also issued /run for immediate fire)"
Write-Host "Expected runtime: ~75s capture + a few seconds startup"
Write-Host "Marker file when done: $env:USERPROFILE\tc_phase12_capture_done.json"
