$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

Write-Host "Cleaning up ALL PowerPoint instances first" -ForegroundColor Yellow
Get-Process POWERPNT, EXCEL -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  Stopping $($_.Name) pid=$($_.Id) Session $($_.SessionId)"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# Verify clean
$remaining = Get-Process POWERPNT, EXCEL -ErrorAction SilentlyContinue
if ($remaining) {
    Write-Host "FAILED to clean: $($remaining.Count) processes still running" -ForegroundColor Red
    $remaining | Select-Object Id, SessionId, Name | Format-Table | Out-String | Write-Host
    exit 2
}
Write-Host "All PowerPoint/Excel processes stopped" -ForegroundColor Green

$psexec = "$env:LOCALAPPDATA\PsTools\PsExec64.exe"
if (-not (Test-Path -LiteralPath $psexec)) {
    Write-Host "PsExec missing - run install_psexec.ps1 first" -ForegroundColor Red
    exit 2
}

# Stage local copies
$localStage = "$env:TEMP\tc_ppttc_demo"
New-Item -ItemType Directory -Path $localStage -Force | Out-Null
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\scripts\build_ppttc_demo.py" "$localStage\build_ppttc_demo.py" -Force
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2.ppttc" "$localStage\demo.ppttc" -Force
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\LAND_template.pptx" "$localStage\template.pptx" -Force

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$localOut = "$localStage\output-$ts.pptx"
$localLog = "$localStage\demo-$ts.log"

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"

# Wrapper cmd that runs the demo, captures output, writes exit code
$wrapPath = "$localStage\wrap-$ts.cmd"
$innerCmd = "$pyExe `"$localStage\build_ppttc_demo.py`" --ppttc `"$localStage\demo.ppttc`" --template-override `"$localStage\template.pptx`" --out `"$localOut`""
@"
@echo off
$innerCmd > "$localLog" 2>&1
echo %ERRORLEVEL% > "${localLog}.exitcode"
"@ | Set-Content -LiteralPath $wrapPath -Encoding ASCII

Write-Host "Inner cmd: $innerCmd"
Write-Host "Wrap: $wrapPath"
Write-Host ""
Write-Host "PsExec -i 1 -d cmd.exe (no existing PowerPoint - Dispatch will start fresh)" -ForegroundColor Cyan
$psexecOut = & $psexec -accepteula -nobanner -i 1 -d cmd.exe /c $wrapPath 2>&1 | Out-String
Write-Host "PsExec response: $($psexecOut -split [Environment]::NewLine | Select-Object -Last 5 | Out-String)"

# Poll for completion
$start = Get-Date
$timeout = 240
while ($true) {
    if (Test-Path -LiteralPath "${localLog}.exitcode") {
        Write-Host "Demo finished" -ForegroundColor Green
        break
    }
    if (((Get-Date) - $start).TotalSeconds -gt $timeout) {
        Write-Host "Timeout after $timeout s - demo may still be running" -ForegroundColor Yellow
        break
    }
    Start-Sleep -Seconds 4
}

if (Test-Path -LiteralPath "${localLog}.exitcode") {
    $exitCode = (Get-Content -LiteralPath "${localLog}.exitcode").Trim() -as [int]
    Write-Host "Exit code: $exitCode"
}
if (Test-Path -LiteralPath $localLog) {
    Write-Host ""
    Write-Host "=== demo log tail ==="
    Get-Content -LiteralPath $localLog -Tail 25 | ForEach-Object { Write-Host "  $_" }
}

if (Test-Path -LiteralPath $localOut) {
    $f = Get-Item -LiteralPath $localOut
    Write-Host ""
    Write-Host "OUTPUT: $($f.FullName) size=$($f.Length) bytes" -ForegroundColor Green
    $macDest = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2-output-PSE-$ts.pptx"
    Copy-Item -LiteralPath $localOut -Destination $macDest -Force
    Write-Host "Ferried: $macDest" -ForegroundColor Green
} else {
    Write-Host "NO OUTPUT FILE at $localOut" -ForegroundColor Red
}

# Cleanup any spawned PowerPoint
Get-Process POWERPNT -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Cleaning up demo POWERPNT pid=$($_.Id) Session $($_.SessionId)" -ForegroundColor Cyan
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
