<#
One-shot Phase 12 /core/ capture. Run this on the Windows VM (RDP, console,
or via SSH if you're back at a desktop later) when you can physically click
the AI Side Pane button in PowerPoint once.

Usage (from VM PowerShell, or `ssh Windows-VM 'powershell ... capture_aicore_oneshot.ps1'`):
  .\capture_aicore_oneshot.ps1                        # 90s capture window (default)
  .\capture_aicore_oneshot.ps1 -DurationSeconds 180   # longer window if needed

What it does:
  1. Kills any zombie PowerPoint, clears Office Resiliency state.
  2. Starts mitmdump on 127.0.0.1:8888, recording to mitm.flow + mitm.har.
  3. Sets system + WinHTTP proxy → mitm.
  4. Pre-places Frida custom handlers (for byte-level BCrypt + WinHttp capture).
  5. Launches frida-trace attached to PowerPoint (which you'll start manually).
  6. Prints "CLICK AI BUTTON NOW" with a countdown.
  7. After the window expires, stops everything and restores proxy.
  8. Prints capture path + traffic summary.

While it's running you do this on the desktop (~30 seconds of clicking):
  a) Open PowerPoint (start menu / pinned tile / however).
  b) Click the "think-cell" tab on the ribbon.
  c) Click the AI Side Pane button in the Elements group.
  d) When the AI dialog opens, type ANY prompt (e.g. "hello") and press Enter.
  e) Wait for the response to appear, then close the dialog.

After the script finishes, copy the capture-dir path it prints, then on Mac:
  python3 ~/code/apps/sales-ops-copilot/scripts/analyze_aicore_capture.py <capture-dir>
#>
param(
    [int]$DurationSeconds = 90,
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
Write-Host " Phase 12 /core/ one-shot capture" -ForegroundColor Cyan
Write-Host " Capture dir: $cap" -ForegroundColor Cyan
Write-Host " Duration:    $DurationSeconds seconds" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Kill zombie PP + clear Resiliency
Write-Host "[1/8] Killing any zombie PowerPoint, clearing Office Resiliency..."
Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$resKey = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency"
foreach ($sub in @("StartupItems", "DisabledItems", "DocumentRecovery", "CrashingAddinList")) {
    $k = "$resKey\$sub"
    if (Test-Path $k) {
        Get-ItemProperty -LiteralPath $k -ErrorAction SilentlyContinue | ForEach-Object {
            $_.PSObject.Properties | Where-Object { $_.Name -notin @("PSPath","PSParentPath","PSChildName","PSDrive","PSProvider") } | ForEach-Object {
                Remove-ItemProperty -LiteralPath $k -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# 2. Pre-place Frida custom handlers (BCrypt byte capture)
Write-Host "[2/8] Pre-placing Frida custom handlers..."
$handlerSrc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\frida_handlers"
$handlerDst = "$cap\__handlers__\bcrypt.dll"
New-Item -ItemType Directory -Path $handlerDst -Force | Out-Null
foreach ($h in @("BCryptCreateHash.js", "BCryptHashData.js", "BCryptFinishHash.js")) {
    $src = Join-Path $handlerSrc $h
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $handlerDst $h) -Force
    }
}
# Also write a custom WinHttpSendRequest handler that dumps headers + body
$winhttpDst = "$cap\__handlers__\winhttp.dll"
New-Item -ItemType Directory -Path $winhttpDst -Force | Out-Null
@'
{
  // WinHttpSendRequest signature:
  //   BOOL WinHttpSendRequest(HINTERNET hRequest, LPCWSTR pwszHeaders, DWORD dwHeadersLength,
  //                           LPVOID lpOptional, DWORD dwOptionalLength, DWORD dwTotalLength,
  //                           DWORD_PTR dwContext);
  onEnter(log, args, state) {
    let headers = '';
    try {
      const headersLen = args[2].toInt32();
      if (!args[1].isNull() && headersLen > 0 && headersLen < 65536) {
        // headersLen is in WIDE chars; readUtf16String takes byte length OR char count
        headers = args[1].readUtf16String(headersLen);
      } else if (!args[1].isNull()) {
        headers = args[1].readUtf16String();
      }
    } catch (e) { headers = '<read err: ' + e.message + '>'; }
    let bodyHex = '';
    try {
      const bodyLen = args[4].toInt32();
      if (!args[3].isNull() && bodyLen > 0 && bodyLen < 65536) {
        const buf = new Uint8Array(args[3].readByteArray(bodyLen));
        let h = '';
        for (let i = 0; i < buf.length; i++) {
          h += buf[i].toString(16).padStart(2, '0');
        }
        bodyHex = h;
      }
    } catch (e) { bodyHex = '<body err: ' + e.message + '>'; }
    state.captured = 'WinHttpSendRequest headers=' + JSON.stringify(headers) +
                     ' body_len=' + args[4].toInt32() + ' body_hex=' + bodyHex;
    log(state.captured);
  },
  onLeave(log, retval, state) {
    log('WinHttpSendRequest ret=' + retval.toInt32());
  }
}
'@ | Set-Content -LiteralPath "$winhttpDst\WinHttpSendRequest.js" -Force

# 3. Locate mitmdump + frida-trace
Write-Host "[3/8] Locating mitmdump + frida-trace..."
$mitmdump = (Get-Command mitmdump -ErrorAction SilentlyContinue).Source
if (-not $mitmdump) { $mitmdump = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe" }
$fridaTrace = (Get-Command frida-trace -ErrorAction SilentlyContinue).Source
if (-not $fridaTrace) { $fridaTrace = "$env:APPDATA\Python\Python313\Scripts\frida-trace.exe" }

if (-not (Test-Path -LiteralPath $mitmdump)) { Write-Host "  ERROR: mitmdump not found"; Stop-Transcript | Out-Null; exit 1 }
Write-Host "  mitmdump:    $mitmdump"
Write-Host "  frida-trace: $fridaTrace ($(Test-Path -LiteralPath $fridaTrace))"

# 4. Start mitmdump
Write-Host "[4/8] Starting mitmdump on 127.0.0.1:8888..."
$mitmHar = "$cap\mitm.har"
$mitmFlow = "$cap\mitm.flow"
$mitmLog = "$cap\mitm.log"
$mitmArgs = @(
    "-p", "8888",
    "--listen-host", "127.0.0.1",
    "--set", "hardump=$mitmHar",
    "-w", $mitmFlow,
    "--set", "console_eventlog_verbosity=info"
)
$mitmProc = Start-Process -FilePath $mitmdump -ArgumentList $mitmArgs `
    -RedirectStandardOutput $mitmLog -RedirectStandardError "$mitmLog.err" `
    -PassThru -WindowStyle Hidden
$mitmProc.Id | Set-Content -LiteralPath "$cap\mitm.pid" -Force
Start-Sleep -Seconds 3
Write-Host "  mitm pid: $($mitmProc.Id)"

# 5. Set system + WinHTTP proxy
Write-Host "[5/8] Setting system proxy → 127.0.0.1:8888..."
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
Set-ItemProperty -Path $reg -Name ProxyServer -Value "127.0.0.1:8888"
Set-ItemProperty -Path $reg -Name ProxyOverride -Value "<local>"
& netsh winhttp set proxy "127.0.0.1:8888" "<local>" 2>&1 | Out-Null

# 6. Big banner — tell user to click
$banner = @"

================================================================
                 ACTION REQUIRED

  1. Open PowerPoint
  2. Click the 'think-cell' tab
  3. Click the AI Side Pane button (Elements group)
  4. Type any prompt and press Enter
  5. Wait for the response

  Capturing for $DurationSeconds seconds...
================================================================

"@
Write-Host $banner -ForegroundColor Yellow

# 7. Optional: start frida-trace if PP is launched within 30s
Write-Host "[6/8] Watching for PowerPoint launch (will attach frida-trace if found)..."
$fridaProc = $null
$fridaStartDeadline = (Get-Date).AddSeconds(45)
$fridaStarted = $false
$endDeadline = (Get-Date).AddSeconds($DurationSeconds)

while ((Get-Date) -lt $endDeadline) {
    $remaining = [int]($endDeadline - (Get-Date)).TotalSeconds
    if (-not $fridaStarted -and (Get-Date) -lt $fridaStartDeadline) {
        $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        if ($pp -and (Test-Path -LiteralPath $fridaTrace)) {
            Write-Host "  PP found pid=$($pp.Id) - attaching frida-trace..." -ForegroundColor Green
            $fridaArgs = @(
                "-p", "$($pp.Id)",
                "-i", "winhttp.dll!WinHttp*",
                "-i", "bcrypt.dll!BCrypt*",
                "-i", "kernelbase.dll!CryptUnprotectData",
                "-o", "$cap\frida.log"
            )
            $fridaProc = Start-Process -FilePath $fridaTrace -ArgumentList $fridaArgs `
                -WorkingDirectory $cap `
                -RedirectStandardOutput "$cap\frida_stdout.log" -RedirectStandardError "$cap\frida_stderr.log" `
                -PassThru -WindowStyle Hidden
            $fridaProc.Id | Set-Content -LiteralPath "$cap\frida.pid" -Force
            $fridaStarted = $true
        }
    }
    Write-Host -NoNewline "`r  [$remaining s remaining]   "
    Start-Sleep -Seconds 1
}
Write-Host ""

# 8. Tear down
Write-Host "[7/8] Stopping capture..."
if ($fridaProc) {
    try { Stop-Process -Id $fridaProc.Id -Force -ErrorAction Stop } catch {}
}
if ($mitmProc) {
    try { Stop-Process -Id $mitmProc.Id -Force -ErrorAction Stop } catch {}
}
Start-Sleep -Seconds 2

Write-Host "[8/8] Restoring proxy..."
& netsh winhttp reset proxy 2>&1 | Out-Null
Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0
Remove-ItemProperty -Path $reg -Name ProxyServer -ErrorAction SilentlyContinue

# Report
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " CAPTURE COMPLETE" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  capture_dir: $cap"
$flowSize = if (Test-Path -LiteralPath $mitmFlow) { (Get-Item -LiteralPath $mitmFlow).Length } else { 0 }
$harSize = if (Test-Path -LiteralPath $mitmHar) { (Get-Item -LiteralPath $mitmHar).Length } else { 0 }
$fridaSize = if (Test-Path -LiteralPath "$cap\frida.log") { (Get-Item -LiteralPath "$cap\frida.log").Length } else { 0 }
Write-Host "  mitm.flow:   $flowSize bytes"
Write-Host "  mitm.har:    $harSize bytes"
Write-Host "  frida.log:   $fridaSize bytes (frida_started=$fridaStarted)"

# Quick sanity: scan flow for /core/ traffic
if ($flowSize -gt 0) {
    Write-Host ""
    Write-Host "Scanning mitm.flow for app.prod.ai traffic..."
    $bytes = [System.IO.File]::ReadAllBytes($mitmFlow)
    $text = [System.Text.Encoding]::ASCII.GetString($bytes)
    $coreHits = ([regex]::Matches($text, "app\.prod\.ai\.think-cell\.com")).Count
    $authHits = ([regex]::Matches($text, "Authorization")).Count
    $bearerHits = ([regex]::Matches($text, "Bearer ")).Count
    Write-Host "  app.prod.ai mentions:    $coreHits"
    Write-Host "  Authorization mentions:  $authHits"
    Write-Host "  Bearer mentions:         $bearerHits"
}

Write-Host ""
Write-Host "Next step (on Mac):"
Write-Host "  python3 ~/code/apps/sales-ops-copilot/scripts/analyze_aicore_capture.py '$cap'"
Write-Host ""
Stop-Transcript | Out-Null
