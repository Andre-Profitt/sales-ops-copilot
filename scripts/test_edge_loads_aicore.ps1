<#
Quick test: does real Microsoft Edge on this VM successfully navigate to the
think-cell AI entry URL? If yes, Cloud Armor accepts Edge but rejects
Playwright/curl_cffi -> we can use real WebView2 with JS bridge polyfill.

Test:
  1. Use Invoke-WebRequest from .NET HttpClient (uses SChannel TLS, same as Edge)
  2. Use msedge.exe in headless mode with --dump-dom — captures the actual
     rendered HTML from a real Chromium-with-Edge-TLS pipeline
  3. Compare both responses
#>
$ErrorActionPreference = "Continue"

$entryUrl = "https://app.prod.ai.think-cell.com/?build=1000220&systemid=P5ORMTUJ5E5Y4AJHTN4E7WHKTA&lang=en-US&theme=light"

Write-Host "=== Test 1: Invoke-WebRequest (.NET SChannel) ==="
try {
    $r = Invoke-WebRequest $entryUrl -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
    Write-Host "  status: $($r.StatusCode)"
    Write-Host "  ct:     $($r.Headers['Content-Type'])"
    Write-Host "  via:    $($r.Headers['Via'])"
    $bodyPreview = if ($r.Content) { $r.Content.Substring(0, [Math]::Min(300, $r.Content.Length)) } else { '' }
    Write-Host "  body:   $bodyPreview"
} catch [System.Net.WebException] {
    $resp = $_.Exception.Response
    if ($resp) {
        $stream = $resp.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $body = $reader.ReadToEnd()
        $body = $body.Substring(0, [Math]::Min(300, $body.Length))
        Write-Host "  status: $([int]$resp.StatusCode)"
        Write-Host "  server: $($resp.Headers['Server']) via: $($resp.Headers['Via'])"
        Write-Host "  body:   $body"
    } else {
        Write-Host "  EXCEPTION: $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "=== Test 2: msedge.exe --headless --dump-dom ==="
$edge = (Resolve-Path "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue).Path
if (-not $edge) { $edge = (Resolve-Path "C:\Program Files\Microsoft\Edge\Application\msedge.exe" -ErrorAction SilentlyContinue).Path }
if (-not $edge) { Write-Host "  msedge.exe not found"; exit 1 }
Write-Host "  edge: $edge"

$dom = & $edge --headless=new --disable-gpu --dump-dom $entryUrl 2>&1
if ($LASTEXITCODE -eq 0 -and $dom) {
    $domStr = $dom -join "`n"
    Write-Host "  dom_len: $($domStr.Length)"
    Write-Host "  first 500 chars of DOM:"
    Write-Host ($domStr.Substring(0, [Math]::Min(500, $domStr.Length)))
} else {
    Write-Host "  edge dump-dom failed: exit=$LASTEXITCODE"
    Write-Host ($dom -join "`n").Substring(0, [Math]::Min(500, ($dom -join "`n").Length))
}

Write-Host ""
Write-Host "=== Test 3: msedge.exe --headless full output (incl. JS errors) ==="
$tmpDir = "$env:TEMP\edge_test_$(Get-Random)"
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
$dumpFile = "$tmpDir\dump.html"
& $edge --headless=new --disable-gpu --user-data-dir=$tmpDir --virtual-time-budget=8000 --run-all-compositor-stages-before-draw --screenshot="$tmpDir\screenshot.png" --window-size=1280,800 $entryUrl 2>&1 | Out-File "$tmpDir\edge_log.txt"
Start-Sleep -Seconds 2
Write-Host "  screenshot: $tmpDir\screenshot.png ($((Get-Item $tmpDir\screenshot.png -ErrorAction SilentlyContinue).Length) bytes)"
Write-Host "  edge_log:   $tmpDir\edge_log.txt"
Get-Content "$tmpDir\edge_log.txt" -ErrorAction SilentlyContinue | Select-Object -Last 20 | ForEach-Object { Write-Host "    $_" }
