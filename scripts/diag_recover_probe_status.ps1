$ErrorActionPreference = "Continue"
Write-Output "=== schtasks tc_recover_probe ==="
schtasks /query /tn tc_recover_probe_20260502132208 /v /fo list 2>&1 | Select-Object -First 15

Write-Output ""
Write-Output "=== logs ==="
foreach ($f in @("tc_recover_probe.log", "tc_recover.log", "tc_clean.log", "tc_qat_chain.log")) {
    $p = "$env:USERPROFILE\$f"
    if (Test-Path $p) {
        $sz = (Get-Item $p).Length
        $mt = (Get-Item $p).LastWriteTime
        Write-Output "  ${f}: size=$sz mt=$mt"
    } else {
        Write-Output "  ${f}: MISSING"
    }
}

Write-Output ""
Write-Output "=== PP ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize

Write-Output ""
Write-Output "=== ribbon json ==="
$rj = "$env:USERPROFILE\tc_ribbon_deep.json"
if (Test-Path $rj) {
    $j = Get-Content $rj -Raw | ConvertFrom-Json
    Write-Output "ts=$($j.timestamp_utc) ribbon_hwnd=$($j.ribbon_hwnd) acc=$($j.accessible_count) cand=$($j.candidate_count)"
} else {
    Write-Output "ribbon json MISSING"
}
