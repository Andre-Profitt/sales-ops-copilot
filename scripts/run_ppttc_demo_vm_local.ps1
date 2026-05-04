$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Kill any stuck Session 0 PowerPoint from previous attempt
Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 } | ForEach-Object {
    Write-Host "Killing stuck Session 0 POWERPNT pid=$($_.Id)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"

# Copy fixtures to local C:\temp\tc_demo so PowerPoint in Session 0 can access them
$localDir = "$env:TEMP\tc_demo"
New-Item -ItemType Directory -Path $localDir -Force | Out-Null

$srcPpttc = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2.ppttc"
$srcTemplate = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\LAND_template.pptx"
$srcDemo = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\build_ppttc_demo.py"

$localPpttc = "$localDir\demo.ppttc"
$localTemplate = "$localDir\template.pptx"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$localOut = "$localDir\output-$ts.pptx"

Copy-Item -LiteralPath $srcPpttc -Destination $localPpttc -Force
Copy-Item -LiteralPath $srcTemplate -Destination $localTemplate -Force

Write-Host "Local fixtures:" -ForegroundColor Cyan
Get-Item -LiteralPath $localPpttc | Select-Object Name, Length | Format-Table -AutoSize | Out-String | Write-Host
Get-Item -LiteralPath $localTemplate | Select-Object Name, Length | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "Running demo with LOCAL paths" -ForegroundColor Cyan

& $pyExe $srcDemo `
    --ppttc $localPpttc `
    --template-override $localTemplate `
    --out $localOut 2>&1

$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host "Demo exit code: $exitCode"

if (Test-Path -LiteralPath $localOut) {
    $f = Get-Item -LiteralPath $localOut
    Write-Host "OUTPUT EXISTS: $($f.FullName) size=$($f.Length)" -ForegroundColor Green

    # Ferry back to Mac
    $macDest = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2-output-$ts.pptx"
    Copy-Item -LiteralPath $localOut -Destination $macDest -Force
    Write-Host "Ferried to: $macDest" -ForegroundColor Green
} else {
    Write-Host "NO OUTPUT FILE at $localOut" -ForegroundColor Red
}

# Always kill Session 0 PowerPoint at end (cleanup)
Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 } | ForEach-Object {
    Write-Host "Cleaning up Session 0 POWERPNT pid=$($_.Id)" -ForegroundColor Cyan
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

exit $exitCode
