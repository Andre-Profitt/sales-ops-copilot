<#
Inspect the latest Phase 12 capture and report what was captured.
#>
$ErrorActionPreference = "Continue"

$capParent = "$env:USERPROFILE\tc_auth"
$cap = Get-ChildItem $capParent -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $cap) {
    Write-Host "No capture dir found under $capParent"
    exit 1
}
Write-Host "=== Capture dir: $($cap.FullName) ==="
Get-ChildItem $cap.FullName -Force | Format-Table Name, Length, LastWriteTime -AutoSize

Write-Host ""
Write-Host "=== mitm.har contents ==="
$har = Join-Path $cap.FullName "mitm.har"
if (Test-Path $har) {
    $size = (Get-Item $har).Length
    Write-Host "har size: $size bytes"
    if ($size -gt 100) {
        try {
            $obj = Get-Content $har -Raw -Encoding UTF8 | ConvertFrom-Json
            $count = $obj.log.entries.Count
            Write-Host "entries: $count"
            $obj.log.entries | Select-Object -First 10 | ForEach-Object {
                $url = $_.request.url
                if ($url.Length -gt 100) { $url = $url.Substring(0, 100) + "..." }
                Write-Host ("  " + $_.request.method + " [" + $_.response.status + "] " + $url)
            }
        } catch {
            Write-Host "har parse failed: $($_.Exception.Message)"
            Get-Content $har -Raw -Encoding UTF8 | Select-Object -First 1
        }
    } else {
        Write-Host "(har is empty or near-empty - no traffic captured by mitmproxy)"
        Get-Content $har -Raw -Encoding UTF8
    }
} else {
    Write-Host "no mitm.har file"
}

Write-Host ""
Write-Host "=== mitm.flow size ==="
$flow = Join-Path $cap.FullName "mitm.flow"
if (Test-Path $flow) {
    Write-Host "flow size: $((Get-Item $flow).Length) bytes"
}

Write-Host ""
Write-Host "=== mitm.log (mitmproxy stdout) ==="
$mlog = Join-Path $cap.FullName "mitm.log"
if (Test-Path $mlog) {
    Get-Content $mlog | Select-Object -First 20
}
$mlogerr = Join-Path $cap.FullName "mitm.log.err"
if (Test-Path $mlogerr) {
    $errSize = (Get-Item $mlogerr).Length
    if ($errSize -gt 0) {
        Write-Host ""
        Write-Host "=== mitm.log.err ($errSize bytes) ==="
        Get-Content $mlogerr | Select-Object -First 20
    }
}

Write-Host ""
Write-Host "=== frida.log + variants ==="
Get-ChildItem $cap.FullName -Filter "*frida*" | ForEach-Object {
    Write-Host ""
    Write-Host "  $($_.Name) ($($_.Length) bytes)"
    if ($_.Length -gt 0 -and $_.Length -lt 50000) {
        Get-Content $_.FullName | Select-Object -First 30 | ForEach-Object { Write-Host "    $_" }
    } elseif ($_.Length -gt 0) {
        Get-Content $_.FullName -TotalCount 30 | ForEach-Object { Write-Host "    $_" }
    }
}
