$ErrorActionPreference = "Continue"

# Stage local copies
$stage = "$env:TEMP\tc_ppttc_cli"
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2.ppttc" "$stage\demo.ppttc" -Force
Copy-Item "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\LAND_template.pptx" "$stage\template.pptx" -Force

# The .ppttc has a `template` field pointing to /private/tmp/... — patch to local
$pptcText = Get-Content -LiteralPath "$stage\demo.ppttc" -Raw
$pptcText = $pptcText -replace '"/private/tmp/LAND_template_manual_candidate\.pptx"', '"C:\\Users\\test\\AppData\\Local\\Temp\\tc_ppttc_cli\\template.pptx"'
Set-Content -LiteralPath "$stage\demo.ppttc" -Value $pptcText -Encoding UTF8

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "$stage\output-$ts.pptx"
$ppttc = "C:\Program Files (x86)\think-cell\ppttc.exe"

Write-Host "=== Attempt 1: ppttc.exe demo.ppttc -o output.pptx ==="
$ec1 = -1
try {
    & $ppttc "$stage\demo.ppttc" -o $out 2>&1 | ForEach-Object { Write-Host "  $_" }
    $ec1 = $LASTEXITCODE
} catch {
    Write-Host "  EXC: $($_.Exception.Message)"
}
Write-Host "Exit code: $ec1"
if (Test-Path -LiteralPath $out) {
    $f = Get-Item -LiteralPath $out
    Write-Host "OUTPUT: $($f.FullName) size=$($f.Length)" -ForegroundColor Green
    $macDest = "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\Jesper-Tyrer-LAND-2026-Q2-output-CLI-$ts.pptx"
    Copy-Item -LiteralPath $out -Destination $macDest -Force
    Write-Host "Ferried: $macDest" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "=== Attempt 2: ppttc.exe demo.ppttc (no -o, see if it auto-names) ==="
Push-Location $stage
$ec2 = -1
try {
    & $ppttc "$stage\demo.ppttc" 2>&1 | ForEach-Object { Write-Host "  $_" }
    $ec2 = $LASTEXITCODE
} catch {
    Write-Host "  EXC: $($_.Exception.Message)"
}
Pop-Location
Write-Host "Exit code: $ec2"
Write-Host "Files in stage after Attempt 2:"
Get-ChildItem -LiteralPath $stage | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String | Write-Host

# Cleanup any spawned PowerPoint
Get-Process POWERPNT, EXCEL -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Cleanup: stopping $($_.Name) pid=$($_.Id) Session $($_.SessionId)"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
