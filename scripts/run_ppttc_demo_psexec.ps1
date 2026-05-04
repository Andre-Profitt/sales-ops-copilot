$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Clean up any stuck Session 0 PowerPoint
Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 } | ForEach-Object {
    Write-Host "Cleaning Session 0 POWERPNT pid=$($_.Id)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

$psexec = "$env:LOCALAPPDATA\PsTools\PsExec64.exe"
if (-not (Test-Path -LiteralPath $psexec)) {
    Write-Host "PsExec missing - run install_psexec.ps1 first" -ForegroundColor Red
    exit 2
}

# Stage local copies of the demo script + fixtures so the Session 1 process doesn't depend on UNC
$localStage = "$env:TEMP\tc_ppttc_demo"
New-Item -ItemType Directory -Path $localStage -Force | Out-Null
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\scripts\build_ppttc_demo.py" "$localStage\build_ppttc_demo.py" -Force
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2.ppttc" "$localStage\demo.ppttc" -Force
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\LAND_template.pptx" "$localStage\template.pptx" -Force

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$localOut = "$localStage\output-$ts.pptx"
$localLog = "$localStage\demo-$ts.log"

# Build the inner command for PsExec
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
$innerCmd = "$pyExe `"$localStage\build_ppttc_demo.py`" --ppttc `"$localStage\demo.ppttc`" --template-override `"$localStage\template.pptx`" --out `"$localOut`""
Write-Host "Inner command: $innerCmd" -ForegroundColor Cyan

# Run via PsExec into Session 1 (interactive) and redirect output to a file
$wrapPath = "$localStage\wrap-$ts.cmd"
@"
@echo off
$innerCmd > "$localLog" 2>&1
echo %ERRORLEVEL% > "${localLog}.exitcode"
"@ | Set-Content -LiteralPath $wrapPath -Encoding ASCII

Write-Host "Firing PsExec -i 1 -d (detached, Session 1)" -ForegroundColor Cyan
$psexecOut = & $psexec -accepteula -nobanner -i 1 -d cmd.exe /c $wrapPath 2>&1 | Out-String
Write-Host "PsExec output:"
Write-Host $psexecOut

# PsExec -d (detached) returns immediately. Poll for exit code file.
$start = Get-Date
$timeout = 240
while ($true) {
    if (Test-Path -LiteralPath "${localLog}.exitcode") {
        Write-Host "Demo finished" -ForegroundColor Green
        break
    }
    if (((Get-Date) - $start).TotalSeconds -gt $timeout) {
        Write-Host "Timeout after $timeout s" -ForegroundColor Yellow
        break
    }
    Start-Sleep -Seconds 4
}

# Read results
if (Test-Path -LiteralPath "${localLog}.exitcode") {
    $exitCode = (Get-Content -LiteralPath "${localLog}.exitcode").Trim() -as [int]
    Write-Host "Exit code: $exitCode"
}
if (Test-Path -LiteralPath $localLog) {
    Write-Host ""
    Write-Host "=== demo log (tail) ==="
    Get-Content -LiteralPath $localLog -Tail 30 | ForEach-Object { Write-Host "  $_" }
}

# Ferry output to Mac
if (Test-Path -LiteralPath $localOut) {
    $f = Get-Item -LiteralPath $localOut
    Write-Host "OUTPUT: $($f.FullName) size=$($f.Length)" -ForegroundColor Green
    $macDest = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2-output-PSE-$ts.pptx"
    Copy-Item -LiteralPath $localOut -Destination $macDest -Force
    Write-Host "Ferried: $macDest" -ForegroundColor Green
} else {
    Write-Host "NO OUTPUT FILE" -ForegroundColor Red
}
