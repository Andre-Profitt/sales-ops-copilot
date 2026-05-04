<#
SSH-triggered wrapper: copies the UIA discovery script to a local VM path,
launches PowerPoint if not running, registers a scheduled task that walks
the UIA tree from Session 1.
#>
$ErrorActionPreference = "Continue"

$srcUnc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\probe_thinkcell_ribbon_uia.ps1"
$localCopy = "$env:USERPROFILE\tc_uia_discovery.ps1"

Copy-Item -LiteralPath $srcUnc -Destination $localCopy -Force
Write-Host "Local copy: $localCopy ($(Get-Item -LiteralPath $localCopy | Select-Object -ExpandProperty Length) bytes)"

# Ensure PowerPoint is running. Use a separate Session-1 task to launch it
# if needed, since SSH-launched POWERPNT goes to Session 0 (invisible).
$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue
if (-not $pp) {
    Write-Host "POWERPNT not running — scheduling cold launch in Session 1"
    $launchScript = @'
$ppExe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $ppExe -ArgumentList "/N"
Start-Sleep -Seconds 6  # let it load + think-cell ribbon initialize
'@
    $launchPath = "$env:USERPROFILE\tc_pp_launch.ps1"
    $launchScript | Set-Content -LiteralPath $launchPath -Force
    $launchTask = "tc_pp_launch_$(Get-Date -Format yyyyMMddHHmmss)"
    $launchCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$launchPath`""
    & schtasks.exe /create /sc once /st (Get-Date).AddMinutes(1).ToString("HH:mm") /tn $launchTask /tr $launchCmd /it /rl limited /f 2>&1 | Out-Null
    & schtasks.exe /run /tn $launchTask 2>&1 | Out-Null
    Write-Host "Launch task: $launchTask — sleeping 8s for PowerPoint to come up"
    Start-Sleep -Seconds 8
} else {
    Write-Host "POWERPNT already running (pid=$($pp.Id))"
}

# Clean stale result
Remove-Item -LiteralPath "$env:USERPROFILE\tc_uia_discovery.json" -Force -ErrorAction SilentlyContinue

# Register UIA discovery task in Session 1
$discTask = "tc_uia_disc_$(Get-Date -Format yyyyMMddHHmmss)"
$discCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$localCopy`""
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $discTask /tr $discCmd /it /rl limited /f 2>&1 | Select-Object -Last 2
& schtasks.exe /run /tn $discTask 2>&1 | Select-Object -Last 1
Write-Host "Discovery task: $discTask"
Write-Host "Result file when done: $env:USERPROFILE\tc_uia_discovery.json"
