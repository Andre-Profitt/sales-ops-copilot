<#
Launch PP fresh (post-QAT-pin) and fire the QAT button UIA probe.
#>
$ErrorActionPreference = "Continue"

Copy-Item -LiteralPath "\\Mac\Home\code\apps\sales-ops-copilot\scripts\probe_qat_button_uia.ps1" `
    -Destination "$env:USERPROFILE\tc_qat_btn.ps1" -Force
Remove-Item "$env:USERPROFILE\tc_qat_button.json" -Force -ErrorAction SilentlyContinue

# Kill any stragglers
Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

# Launch PP via schtask
$launchPath = "$env:USERPROFILE\tc_pp_launch.ps1"
@'
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $exe -ArgumentList "/N"
Start-Sleep -Seconds 25
'@ | Set-Content -LiteralPath $launchPath -Force
$launchTn = "tc_pp_launch_$(Get-Date -Format yyyyMMddHHmmss)"
& schtasks.exe /create /sc once /st (Get-Date).AddMinutes(1).ToString("HH:mm") /tn $launchTn /tr "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$launchPath`"" /it /rl limited /f 2>&1 | Out-Null
& schtasks.exe /run /tn $launchTn 2>&1 | Out-Null

# Wait for PP MainWindowTitle to populate (up to 120s — PP cold-start can be slow)
$deadline = (Get-Date).AddSeconds(120)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Host "PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"; break }
    Start-Sleep -Milliseconds 500
}
if (-not $pp) {
    Write-Host "WARNING: no PP after 120s"
    # Diagnose remaining state
    $procs = Get-Process POWERPNT -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        Write-Host "  pp pid=$($p.Id) handle=$($p.MainWindowHandle) title='$($p.MainWindowTitle)' resp=$($p.Responding)"
    }
    exit 1
}
Start-Sleep -Seconds 4  # let ribbon stabilize

# Fire the probe via schtask (so it runs in Session 1)
$tn = "tc_qat_btn_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\tc_qat_btn.ps1`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Host "Triggered: $tn"
