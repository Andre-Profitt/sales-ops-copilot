$ErrorActionPreference = "Continue"
$dirs = Get-ChildItem -LiteralPath $env:TEMP -Filter "tcrender_*" -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 2
foreach ($d in $dirs) {
    Write-Host "=== dir: $($d.FullName) ==="
    Write-Host "Modified: $($d.LastWriteTime)"
    Get-ChildItem -LiteralPath $d.FullName | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String | Write-Host
    Write-Host "--- staged .ppttc first 8 lines ---"
    $ppttc = Get-ChildItem -LiteralPath $d.FullName -Filter "*.ppttc" | Select-Object -First 1
    if ($ppttc) {
        Get-Content -LiteralPath $ppttc.FullName | Select-Object -First 8 | ForEach-Object { Write-Host "  $_" }
    }
    Write-Host ""
}

# Also try running ppttc.exe manually on the latest staged dir to see what it does
$latest = $dirs | Select-Object -First 1
if ($latest) {
    $ppttc = Get-ChildItem -LiteralPath $latest.FullName -Filter "*.ppttc" | Select-Object -First 1
    if ($ppttc) {
        Write-Host "=== manual ppttc.exe run on staged input ==="
        $out = "$($latest.FullName)\manual-test-output.pptx"
        & "C:\Program Files (x86)\think-cell\ppttc.exe" $ppttc.FullName -o $out 2>&1 | ForEach-Object { Write-Host "  $_" }
        Write-Host "  Exit: $LASTEXITCODE"
        if (Test-Path -LiteralPath $out) {
            $f = Get-Item -LiteralPath $out
            Write-Host "  OUTPUT: $($f.FullName) size=$($f.Length)"
        } else {
            Write-Host "  NO OUTPUT"
        }
    }
}
