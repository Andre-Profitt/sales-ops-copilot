$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Ensure no Session 0 PowerPoint is hanging from prior runs
Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq 0 } | ForEach-Object {
    Write-Host "Cleaning up stuck Session 0 POWERPNT pid=$($_.Id)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# Build the actual demo command file
$demoScript = @'
$ErrorActionPreference = "Continue"
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2-output-S1-$ts.pptx"
Write-Output "[demo] target output: $out"
& $pyExe "\\Mac\Home\code\apps\sales-ops-copilot\scripts\build_ppttc_demo.py" `
    --ppttc "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2.ppttc" `
    --template-override "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\LAND_template.pptx" `
    --out $out 2>&1
Write-Output "[demo] exit code: $LASTEXITCODE"
if (Test-Path -LiteralPath $out) {
    $f = Get-Item -LiteralPath $out
    Write-Output "[demo] OUTPUT: $($f.FullName) size=$($f.Length)"
} else {
    Write-Output "[demo] NO OUTPUT FILE"
}
exit $LASTEXITCODE
'@

$demoFile = "$env:TEMP\tc_demo_inner_$([guid]::NewGuid().ToString('N').Substring(0, 8)).ps1"
Set-Content -LiteralPath $demoFile -Value $demoScript -Encoding UTF8
Write-Host "Demo inner script: $demoFile"

# Output dir for the session1 runner verdict
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\ppttc_demo_session1\$ts"

& "\\Mac\Home\code\apps\sales-ops-copilot\scripts\run_in_session1.ps1" `
    -Command $demoFile `
    -OutputDir $outDir `
    -TimeoutSeconds 240

Remove-Item -LiteralPath $demoFile -Force -ErrorAction SilentlyContinue
