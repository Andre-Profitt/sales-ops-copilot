<# SSH-trigger the PP recovery via schtask (so SendKeys reaches Session 1). #>
$ErrorActionPreference = "Continue"
Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\recover_pp_startup.ps1" `
    -Destination "$env:USERPROFILE\tc_recover.ps1" -Force

# Also write a marker we can poll for
Remove-Item "$env:USERPROFILE\tc_recover.log" -Force -ErrorAction SilentlyContinue

$tn = "tc_recover_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_recover.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
