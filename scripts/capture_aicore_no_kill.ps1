<#
Capture /core/ traffic WITHOUT killing your PowerPoint session.
You keep PP open. Script just sets up mitm + frida + proxy and waits.
You click the AI button at your pace.
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
Write-Host " /core/ capture (NO PP kill, 5 min window)" -ForegroundColor Cyan
Write-Host " Capture dir: $cap" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Custom Frida handlers
Write-Host "[1/5] Pre-placing Frida custom handlers..."
$handlerSrc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\frida_handlers"
$handlerDst = "$cap\__handlers__\bcrypt.dll"
New-Item -ItemType Directory -Path $handlerDst -Force | Out-Null
foreach ($h in @("BCryptCreateHash.js", "BCryptHashData.js", "BCryptFinishHash.js")) {
    $src = Join-Path $handlerSrc $h
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $handlerDst $h) -Force
    }
}

# WinHttpSendRequest custom handler
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
    log('WinHttpSendRequest headers=' + JSON.stringify(headers) +
        ' body_len=' + args[4].toInt32() + ' body_hex=' + bodyHex);
  },
  onLeave(log, retval, state) { log('WinHttpSendRequest ret=' + retval.toInt32()); }
}
'@ | Set-Content -LiteralPath "$winhttpDst\WinHttpSendRequest.js" -Force

# Locate tools
$mitmdump = (Get-Command mitmdump -ErrorAction SilentlyContinue).Source
if (-not $mitmdump) { $mitmdump = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe" }
$fridaTrace = (Get-Command frida-trace -ErrorAction SilentlyContinue).Source
if (-not $fridaTrace) { $fridaTrace = "$env:APPDATA\Python\Python313\Scripts\frida-trace.exe" }

Write-Host "[2/5] Starting mitmdump..."
$mitmHar = "$cap\mitm.har"
$mitmFlow = "$cap\mitm.flow"
$mitmLog = "$cap\mitm.log"
$mitmArgs = @("-p", "8888", "--listen-host", "127.0.0.1", "--set", "hardump=$mitmHar", "-w", $mitmFlow)
$mitmProc = Start-Process -FilePath $mitmdump -ArgumentList $mitmArgs `
    -RedirectStandardOutput $mitmLog -RedirectStandardError "$mitmLog.err" `
    -PassThru -WindowStyle Hidden
Start-Sleep 2
Write-Host "  mitm pid: $($mitmProc.Id)"

Write-Host "[3/5] Setting proxy..."
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
Set-ItemProperty -Path $reg -Name ProxyServer -Value "127.0.0.1:8888"
& netsh winhttp set proxy "127.0.0.1:8888" "<local>" 2>&1 | Out-Null

Write-Host "[4/5] Attaching frida-trace if PP is running..."
$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($pp -and (Test-Path $fridaTrace)) {
    $fridaArgs = @("-p", "$($pp.Id)", "-i", "winhttp.dll!WinHttp*", "-i", "bcrypt.dll!BCrypt*", "-o", "$cap\frida.log")
    $fridaProc = Start-Process -FilePath $fridaTrace -ArgumentList $fridaArgs `
        -WorkingDirectory $cap `
        -RedirectStandardOutput "$cap\frida_stdout.log" -RedirectStandardError "$cap\frida_stderr.log" `
        -PassThru -WindowStyle Hidden
    Write-Host "  frida pid: $($fridaProc.Id) (attached to PP pid $($pp.Id))"
} else {
    Write-Host "  PP not running with window -- frida skipped (mitm still captures)"
}

# BIG BANNER
$banner = @"

================================================================
  CAPTURE IS LIVE -- $DurationSeconds seconds

  YOUR POWERPOINT IS UNTOUCHED. Use it normally:

    1. Switch to PowerPoint
    2. Click 'think-cell' tab
    3. Click 'AI Side Pane' button (Elements group)
    4. Type any prompt + Enter
    5. Wait for AI response
    6. /core/ traffic flows through mitm -- captured

  Take your time. Capture runs for 5 minutes total.
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
Write-Host "[5/5] Stopping capture..."
if ($fridaProc) { try { Stop-Process -Id $fridaProc.Id -Force -ErrorAction Stop } catch {} }
try { Stop-Process -Id $mitmProc.Id -Force -ErrorAction Stop } catch {}
Start-Sleep 2

& netsh winhttp reset proxy 2>&1 | Out-Null
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0

# Report
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " CAPTURE COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
$flowSize = if (Test-Path $mitmFlow) { (Get-Item $mitmFlow).Length } else { 0 }
$fridaSize = if (Test-Path "$cap\frida.log") { (Get-Item "$cap\frida.log").Length } else { 0 }
Write-Host "  capture_dir: $cap"
Write-Host "  mitm.flow:   $flowSize bytes"
Write-Host "  frida.log:   $fridaSize bytes"

# Quick scan
if ($flowSize -gt 0) {
    $bytes = [System.IO.File]::ReadAllBytes($mitmFlow)
    $text = [System.Text.Encoding]::ASCII.GetString($bytes)
    $coreHits = ([regex]::Matches($text, "app\.prod\.ai")).Count
    Write-Host "  app.prod.ai mentions: $coreHits"
    if ($coreHits -gt 0) {
        Write-Host "  ** /core/ TRAFFIC CAPTURED -- success **" -ForegroundColor Green
    } else {
        Write-Host "  no /core/ traffic captured (AI button not clicked or proxy bypassed)" -ForegroundColor Yellow
    }
}
Stop-Transcript | Out-Null
