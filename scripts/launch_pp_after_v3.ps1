<# Schedule PP launch in Session 1 to fire ~30s from now (after v3 banner appears). #>
$ErrorActionPreference = "Continue"

# Wrapper batch that uses Start-Process to open PP visibly
$bat = "C:\Users\test\tc_pp_launcher.bat"
@'
@echo off
start "" "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE" /N
'@ | Set-Content -LiteralPath $bat -Encoding ASCII -Force

$tn = "tc_pp_relaunch_$(Get-Date -Format yyyyMMddHHmmss)"
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $bat /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1
Write-Output "PP launch scheduled: $tn"
