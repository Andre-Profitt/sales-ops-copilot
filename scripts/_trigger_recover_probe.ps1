$ErrorActionPreference = "Continue"
$here = "\\Mac\Home\code\apps\sales-ops-copilot\scripts"
Copy-Item -LiteralPath "$here\run_recover_then_ribbon_probe.ps1" -Destination "$env:USERPROFILE\tc_recover_probe.ps1" -Force
Copy-Item -LiteralPath "$here\probe_thinkcell_ribbon_deep.ps1" -Destination "$env:USERPROFILE\tc_ribbon.ps1" -Force
Remove-Item "$env:USERPROFILE\tc_recover_probe.log" -Force -ErrorAction SilentlyContinue

$tn = "tc_recover_probe_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_recover_probe.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
