<#
Trigger the QAT pin + PP launch + UIA probe chain via Session-1 schtask.
Stages all dependent scripts to %USERPROFILE% first.
#>
$ErrorActionPreference = "Continue"

$here = "\\Mac\Home\code\apps\sales-ops-copilot\scripts"
Copy-Item -LiteralPath "$here\run_qat_pin_and_probe.ps1" -Destination "$env:USERPROFILE\tc_qat_chain.ps1" -Force
Copy-Item -LiteralPath "$here\probe_qat_pin_aisidepane.ps1" -Destination "$env:USERPROFILE\tc_qat.ps1" -Force
Copy-Item -LiteralPath "$here\probe_qat_button_uia.ps1" -Destination "$env:USERPROFILE\tc_qat_btn.ps1" -Force

Remove-Item "$env:USERPROFILE\tc_qat_chain.log" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\tc_qat_button.json" -Force -ErrorAction SilentlyContinue

$tn = "tc_qat_chain_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_qat_chain.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
