<#
Roll back Office 365 from 19929 (broken) to 19822.20182 (last known good).

Microsoft acknowledged regression in 19929 affecting third-party COM interop
(ref: MS Q&A 5874363). Rollback is reversible: run OfficeC2RClient.exe /update
with no version pin to return to current.

Usage on VM:
  powershell ... rollback_office_to_19822.ps1            (silent rollback)
  powershell ... rollback_office_to_19822.ps1 -Visible   (shows MS update UI on desktop)
#>
param(
    [switch]$Visible,
    [string]$TargetVersion = "16.0.19822.20182"
)
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\office_rollback.log" -Force | Out-Null

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Office rollback: 19929 -> $TargetVersion" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Verify current version
$reg = "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration"
if (Test-Path $reg) {
    $cur = (Get-ItemProperty $reg).VersionToReport
    Write-Host "Current version: $cur"
    if ($cur -eq $TargetVersion) {
        Write-Host "Already at target version. Nothing to do."
        Stop-Transcript | Out-Null
        exit 0
    }
}

# 2. Close all Office apps
Write-Host "[1] Closing all Office apps..."
foreach ($name in @("POWERPNT", "EXCEL", "WINWORD", "OUTLOOK", "ONENOTE", "MSACCESS", "MSPUB", "VISIO", "WINPROJ")) {
    $procs = Get-Process $name -ErrorAction SilentlyContinue
    if ($procs) {
        Write-Host "  Stopping $name ($($procs.Count))"
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 3

# 3. Locate OfficeC2RClient.exe
$c2r = "C:\Program Files\Common Files\Microsoft Shared\ClickToRun\OfficeC2RClient.exe"
if (-not (Test-Path $c2r)) {
    Write-Host "[!] OfficeC2RClient.exe not at $c2r" -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 1
}
Write-Host "[2] OfficeC2RClient.exe: $c2r"

# 4. Fire the rollback
$displayLevel = if ($Visible) { "true" } else { "false" }
$args = @(
    "/update", "user",
    "updatetoversion=$TargetVersion",
    "displaylevel=$displayLevel",
    "forceappshutdown=true"
)
Write-Host "[3] Firing: OfficeC2RClient.exe $($args -join ' ')"
Write-Host "    (this returns immediately; the actual update runs in OfficeClickToRun service)"

$proc = Start-Process -FilePath $c2r -ArgumentList $args -PassThru -Wait
Write-Host "[4] OfficeC2RClient.exe exited with code: $($proc.ExitCode)"

# 5. Poll for the update to actually finish (version registry to flip)
Write-Host "[5] Waiting for ClickToRun service to flip the version registry..."
$deadline = (Get-Date).AddMinutes(20)
$prev = (Get-ItemProperty $reg).VersionToReport
$lastReport = Get-Date
while ((Get-Date) -lt $deadline) {
    $now = (Get-ItemProperty $reg -ErrorAction SilentlyContinue).VersionToReport
    if ($now -eq $TargetVersion) {
        Write-Host "[6] Version flipped to: $now"
        break
    }
    if ($now -ne $prev) {
        Write-Host "  version changed: $prev -> $now"
        $prev = $now
    }
    # Periodic progress
    if (((Get-Date) - $lastReport).TotalSeconds -gt 30) {
        $c2rProc = Get-Process OfficeClickToRun -ErrorAction SilentlyContinue
        $c2rState = if ($c2rProc) { "running pid=$($c2rProc.Id) cpu=$([Math]::Round($c2rProc.CPU,1))s" } else { "not running" }
        Write-Host "  [poll] version=$now   ClickToRun: $c2rState"
        $lastReport = Get-Date
    }
    Start-Sleep -Seconds 5
}

# 6. Final state
$final = (Get-ItemProperty $reg -ErrorAction SilentlyContinue).VersionToReport
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
$ppVer = if (Test-Path $ppExe) { (Get-Item $ppExe).VersionInfo.FileVersion } else { "(missing)" }

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " ROLLBACK COMPLETE"
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  registry VersionToReport: $final"
Write-Host "  POWERPNT.EXE FileVersion: $ppVer"
if ($final -eq $TargetVersion) {
    Write-Host "  STATUS: SUCCESS" -ForegroundColor Green
} else {
    Write-Host "  STATUS: did not reach target $TargetVersion in 20 min" -ForegroundColor Yellow
    Write-Host "         (it may still be running; check OfficeClickToRun service)"
}
Stop-Transcript | Out-Null
