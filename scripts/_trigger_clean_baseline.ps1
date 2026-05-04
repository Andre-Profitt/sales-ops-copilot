$ErrorActionPreference = "Continue"
Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\recover_clean_baseline.ps1" `
    -Destination "$env:USERPROFILE\tc_clean.ps1" -Force
Remove-Item "$env:USERPROFILE\tc_clean.log" -Force -ErrorAction SilentlyContinue

$tn = "tc_clean_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_clean.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
