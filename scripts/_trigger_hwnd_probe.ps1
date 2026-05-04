<#
SSH-triggered wrapper for the HWND-MSAA probe.
#>
$ErrorActionPreference = "Continue"

Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\probe_thinkcell_ribbon_hwnds.ps1" `
    -Destination "$env:USERPROFILE\tc_hwnds.ps1" -Force
Remove-Item "$env:USERPROFILE\tc_hwnds.json" -Force -ErrorAction SilentlyContinue

# Ensure PowerPoint is running
$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    Write-Host "Launching PowerPoint via Session-1 task (no PP running)"
    $launchPath = "$env:USERPROFILE\tc_pp_launch.ps1"
    @'
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $exe -ArgumentList "/N"
Start-Sleep -Seconds 12
'@ | Set-Content -LiteralPath $launchPath -Force
    $launchTn = "tc_pp_launch_$(Get-Date -Format yyyyMMddHHmmss)"
    & schtasks.exe /create /sc once /st (Get-Date).AddMinutes(1).ToString("HH:mm") /tn $launchTn /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$launchPath`"" /it /rl limited /f 2>&1 | Out-Null
    & schtasks.exe /run /tn $launchTn 2>&1 | Out-Null
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
        if ($pp) { Write-Host "PowerPoint up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $pp) { Write-Host "WARNING: PowerPoint didn't come up within 60s" }
}

$tn = "tc_hwnds_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_hwnds.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
