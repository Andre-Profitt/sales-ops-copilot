$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
if (-not (Test-Path -LiteralPath $pyExe)) {
    Write-Host "x64 Python missing at $pyExe" -ForegroundColor Red
    exit 2
}

# Make sure tc_com_driver is installed editable (smoke already did this)
$check = & $pyExe -c "import tc_com_driver; print(tc_com_driver.__file__)" 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing tc_com_driver editable" -ForegroundColor Cyan
    & $pyExe -m pip install --user --no-warn-script-location -e "\\Mac\Home\code\apps\sales-ops-copilot\libs\tc_com_driver" 2>&1 | Select-Object -Last 3
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2-output-$ts.pptx"

Write-Host "Running .ppttc demo - target output: $out" -ForegroundColor Cyan

& $pyExe "\\Mac\Home\code\apps\sales-ops-copilot\scripts\build_ppttc_demo.py" `
    --ppttc "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2.ppttc" `
    --template-override "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\LAND_template.pptx" `
    --out $out 2>&1

$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host "Demo exit code: $exitCode" -ForegroundColor (if ($exitCode -eq 0) { "Green" } else { "Red" })
if (Test-Path -LiteralPath $out) {
    $f = Get-Item -LiteralPath $out
    Write-Host "Output: $($f.FullName) ($($f.Length) bytes)" -ForegroundColor Green
} else {
    Write-Host "No output file at $out" -ForegroundColor Red
}
exit $exitCode
