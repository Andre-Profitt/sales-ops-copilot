<#
v3 capture: forces WebView2 to:
  (a) disable HTTP/3 / QUIC (so WSS goes over TCP through mitm proxy)
  (b) use 127.0.0.1:8888 as proxy (so even direct connections route through mitm)
  (c) ignore mitm's cert (so the WSS upgrade succeeds via mitm)

Sets WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS persistently (User env var), then runs
the no-kill capture. PP MUST be relaunched after this script sets env vars
for the changes to take effect (any running WebView2 already spawned won't pick them up).

Usage:
  powershell -File capture_aicore_v3_no_http3.ps1 -DurationSeconds 300
#>
param(
    [int]$DurationSeconds = 300,
    [string]$CaptureRoot = "$env:USERPROFILE\tc_aicore_captures"
)
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$cap = Join-Path $CaptureRoot $ts
New-Item -ItemType Directory -Path $cap -Force | Out-Null
Start-Transcript -Path "$cap\run.log" -Force | Out-Null

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " /core/ WSS capture v3 (HTTP/3 disabled)" -ForegroundColor Cyan
Write-Host " Capture dir: $cap" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# 1. Set WebView2 env vars to force HTTP/2 + proxy + cert ignore
Write-Host ""
Write-Host "[1/6] Setting WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS..."
$wvArgs = "--disable-quic --disable-http3 --proxy-server=127.0.0.1:8888 --proxy-bypass-list=`"<-loopback>`" --ignore-certificate-errors --disable-features=AsyncDns"
[Environment]::SetEnvironmentVariable('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', $wvArgs, 'User')
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $wvArgs
Write-Host "  set: $wvArgs"
Write-Host "  WARNING: PowerPoint MUST be CLOSED+REOPENED for env var to take effect"

# 2. Kill any PP / msedgewebview2 so they pick up the new env var on next launch
Write-Host ""
Write-Host "[2/6] Killing PP + WebView2 instances (so they pick up new env vars on next launch)..."
$killed = Get-Process POWERPNT, msedgewebview2 -ErrorAction SilentlyContinue
$killed | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 3
Write-Host "  killed $($killed.Count)"

# 3. Place Frida + WinHttp custom handlers
Write-Host ""
Write-Host "[3/6] Pre-placing Frida custom handlers..."
$handlerSrc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\frida_handlers"
$handlerDst = "$cap\__handlers__\bcrypt.dll"
New-Item -ItemType Directory -Path $handlerDst -Force | Out-Null
foreach ($h in @("BCryptCreateHash.js", "BCryptHashData.js", "BCryptFinishHash.js")) {
    $src = Join-Path $handlerSrc $h
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $handlerDst $h) -Force
    }
}
$winhttpDst = "$cap\__handlers__\winhttp.dll"
New-Item -ItemType Directory -Path $winhttpDst -Force | Out-Null
@'
{
  onEnter(log, args, state) {
    let headers = '';
    try {
      const headersLen = args[2].toInt32();
      if (!args[1].isNull() && headersLen > 0 && headersLen < 65536) {
        headers = args[1].readUtf16String(headersLen);
      }
    } catch (e) { headers = '<read err>'; }
    let bodyHex = '';
    try {
      const bodyLen = args[4].toInt32();
      if (!args[3].isNull() && bodyLen > 0 && bodyLen < 65536) {
        const buf = new Uint8Array(args[3].readByteArray(bodyLen));
        let h = '';
        for (let i = 0; i < buf.length; i++) h += buf[i].toString(16).padStart(2, '0');
        bodyHex = h;
      }
    } catch (e) {}
    log('WinHttpSendRequest headers=' + JSON.stringify(headers) + ' body_len=' + args[4].toInt32() + ' body_hex=' + bodyHex);
  },
  onLeave(log, retval, state) { log('WinHttpSendRequest ret=' + retval.toInt32()); }
}
'@ | Set-Content -LiteralPath "$winhttpDst\WinHttpSendRequest.js" -Force

# 4. Locate tools + start mitmdump
Write-Host ""
Write-Host "[4/6] Starting mitmdump on 127.0.0.1:8888..."
$mitmdump = (Get-Command mitmdump -ErrorAction SilentlyContinue).Source
if (-not $mitmdump) { $mitmdump = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe" }
$mitmHar = "$cap\mitm.har"
$mitmFlow = "$cap\mitm.flow"
$mitmLog = "$cap\mitm.log"
$mitmArgs = @("-p", "8888", "--listen-host", "127.0.0.1", "--set", "hardump=$mitmHar", "-w", $mitmFlow)
$mitmProc = Start-Process -FilePath $mitmdump -ArgumentList $mitmArgs `
    -RedirectStandardOutput $mitmLog -RedirectStandardError "$mitmLog.err" `
    -PassThru -WindowStyle Hidden
Start-Sleep 2
Write-Host "  mitm pid: $($mitmProc.Id)"

# 5. Set system proxy
Write-Host ""
Write-Host "[5/6] Setting system + WinHTTP proxy..."
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
Set-ItemProperty -Path $reg -Name ProxyServer -Value "127.0.0.1:8888"
& netsh winhttp set proxy "127.0.0.1:8888" "<local>" 2>&1 | Out-Null

# 6. Big banner
$banner = @"

================================================================
  CAPTURE LIVE -- $DurationSeconds seconds (5 min)

  ACTION:
    1. Open PowerPoint NOW (Start menu)
    2. Wait for think-cell tab to load
    3. Click 'think-cell' tab -> AI Side Pane
    4. Type 'show me revenue 100 200 300' -> Enter
    5. Wait for AI response
    6. /core/ WSS frames will be captured this time
       (HTTP/3 disabled = WSS goes through proxy)

================================================================

"@
Write-Host $banner -ForegroundColor Yellow

# Countdown
$endDeadline = (Get-Date).AddSeconds($DurationSeconds)
while ((Get-Date) -lt $endDeadline) {
    $remaining = [int]($endDeadline - (Get-Date)).TotalSeconds
    Write-Host -NoNewline "`r  [$remaining s remaining]   "
    Start-Sleep 1
}
Write-Host ""

# Tear down
Write-Host "[6/6] Stopping capture + restoring proxy..."
try { Stop-Process -Id $mitmProc.Id -Force -ErrorAction Stop } catch {}
Start-Sleep 2
& netsh winhttp reset proxy 2>&1 | Out-Null
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0
# Don't unset WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS yet; user may want to re-run

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " CAPTURE COMPLETE"
Write-Host "================================================" -ForegroundColor Green
$flowSize = if (Test-Path $mitmFlow) { (Get-Item $mitmFlow).Length } else { 0 }
Write-Host "  capture_dir: $cap"
Write-Host "  mitm.flow:   $flowSize bytes"

# Quick scan for WS upgrade to app.prod.ai/core
if ($flowSize -gt 0) {
    $bytes = [System.IO.File]::ReadAllBytes($mitmFlow)
    $text = [System.Text.Encoding]::ASCII.GetString($bytes)
    $coreHits = ([regex]::Matches($text, "app\.prod\.ai\.think-cell\.com")).Count
    $wsHits = ([regex]::Matches($text, "Sec-WebSocket")).Count
    $upgradeHits = ([regex]::Matches($text, "(?i)upgrade.*websocket")).Count
    Write-Host "  app.prod.ai mentions: $coreHits"
    Write-Host "  Sec-WebSocket mentions: $wsHits"
    Write-Host "  WebSocket upgrade mentions: $upgradeHits"
    if ($wsHits -gt 0) {
        Write-Host "  ** WebSocket frames likely captured **" -ForegroundColor Green
    }
}

Stop-Transcript | Out-Null

Write-Host ""
Write-Host "TO DISABLE PROXY ENV VAR FOR NORMAL USE LATER, RUN:"
Write-Host "  [Environment]::SetEnvironmentVariable('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '$null', 'User')"
