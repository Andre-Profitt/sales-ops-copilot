<#
SSH-triggered wrapper for the QAT-pin probe. Schedules the pin script as a
Session-1 task. The pin script kills PowerPoint internally before editing
PowerPoint.officeUI (per Microsoft warning that editing while PP is running
can corrupt the file).

Usage from Mac:
  ssh Windows-VM 'powershell ... _trigger_qat_pin.ps1'                   # pin
  ssh Windows-VM 'powershell ... _trigger_qat_pin.ps1 -RemoteRestore'    # restore
#>
param(
    [switch]$RemoteRestore
)
$ErrorActionPreference = "Continue"

Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\probe_qat_pin_aisidepane.ps1" `
    -Destination "$env:USERPROFILE\tc_qat.ps1" -Force
Remove-Item "$env:USERPROFILE\tc_qat_pin.json" -Force -ErrorAction SilentlyContinue

$tn = "tc_qat_$(Get-Date -Format yyyyMMddHHmmss)"
$arg = if ($RemoteRestore) { " -Restore" } else { "" }
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_qat.ps1`"$arg"
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
