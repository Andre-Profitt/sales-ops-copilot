#requires -Version 5.1
<#
Phase 12 capture - START.

Run this from an admin PowerShell on the VM desktop (Session 1) - NOT via SSH from Mac
(Frida cross-session attach to POWERPNT is unreliable from Session 0).

Pre-conditions:
- Phase 12 setup complete: x64 Python + mitmdump + frida-tools + CA trusted in
  LocalMachine\Root (verified via check_phase12_ready.ps1).
- PowerPoint already open with think-cell ribbon visible, on an empty .pptx, no AI
  feature triggered yet.
- aiauthentication.bin will be backed up + deleted to force token refresh.

This script:
1. Backs up aiauthentication.bin
2. Removes it (forces refresh)
3. Starts mitmdump in background, capturing to ~/tc_auth/<ts>/
4. Sets the system proxy to 127.0.0.1:8888
5. Attaches frida-trace to POWERPNT.EXE in background

Then YOU (interactively):
6. Trigger ONE AI feature in PowerPoint (text/chart suggestion etc.)
7. Wait for the response to render
8. Run stop_phase12_capture.ps1 to wind down + restore.
#>

$ProgressPreference = "SilentlyContinue"
function Log($m, $c="Cyan") { Write-Host "[start] $m" -ForegroundColor $c }

# Resolve mitmdump + frida-trace
$mitmdump = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe"
$fridaTrace = "$env:APPDATA\Python\Python313\Scripts\frida-trace.exe"
foreach ($p in @($mitmdump, $fridaTrace)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Log "Missing: $p" Red
        Log "Re-run setup_phase12_x64_python_mitm.ps1 first" Red
        exit 2
    }
}

# Capture dir
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$cap = "$env:USERPROFILE\tc_auth\$ts"
New-Item -ItemType Directory -Path $cap -Force | Out-Null
Log "Capture dir: $cap"

# Save state-handles file so stop script can find the right session
$state = "$env:USERPROFILE\tc_auth\.current_session"
@{ ts = $ts; capture_dir = $cap } | ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8

# 1. Backup + delete aiauthentication.bin to force refresh
$tc = "$env:APPDATA\think-cell"
$aiauth = "$tc\aiauthentication.bin"
$bak = "$tc\aiauthentication.bin.bak"
if (Test-Path -LiteralPath $aiauth) {
    Copy-Item -LiteralPath $aiauth -Destination $bak -Force
    Remove-Item -LiteralPath $aiauth -Force
    Log "Backed up + removed $aiauth (forces refresh on next AI call)" Green
} else {
    Log "aiauthentication.bin not present - already gone or never there" Yellow
}

# 2. Find POWERPNT pid
$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pp) {
    Log "POWERPNT not running. Open PowerPoint with think-cell first." Red
    exit 1
}
Log "POWERPNT pid: $($pp.Id)"

# 3. Start mitmdump in background
$mitmHar = "$cap\mitm.har"
$mitmFlow = "$cap\mitm.flow"
$mitmLog = "$cap\mitm.log"
$mitmFilter = "~h (aiauthentication|cdnauthentication|ai\.appcom|app\.prod\.ai|prod\.ai)\.think-cell\.com"

$mitmArgs = @(
    "-p", "8888",
    "--listen-host", "127.0.0.1",
    "--set", "hardump=$mitmHar",
    "-w", $mitmFlow,
    "--set", "anticache=true",
    "--view-filter", $mitmFilter
)
$mitmProc = Start-Process -FilePath $mitmdump -ArgumentList $mitmArgs `
    -RedirectStandardOutput $mitmLog -RedirectStandardError "$mitmLog.err" `
    -WindowStyle Hidden -PassThru
Set-Content -LiteralPath "$cap\mitm.pid" -Value $mitmProc.Id
Log "mitmdump started, pid=$($mitmProc.Id), log=$mitmLog" Green

# Give mitmdump a beat to bind the port
Start-Sleep -Seconds 2
if ($mitmProc.HasExited) {
    Log "mitmdump exited immediately - check $mitmLog.err" Red
    Get-Content -LiteralPath "$mitmLog.err" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    exit 1
}

# 4. Set system proxy
Log "Setting WinHTTP + IE proxy to 127.0.0.1:8888"
& netsh winhttp set proxy 127.0.0.1:8888 | Out-Null
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name "ProxyEnable" -Value 1
Set-ItemProperty -Path $reg -Name "ProxyServer" -Value "127.0.0.1:8888"

# 5. Attach frida-trace
$fridaLog = "$cap\frida.log"
$fridaArgs = @(
    "-p", "$($pp.Id)",
    "-i", "winhttp.dll!WinHttpSendRequest",
    "-i", "winhttp.dll!WinHttpWriteData",
    "-i", "winhttp.dll!WinHttpReceiveResponse",
    "-i", "winhttp.dll!WinHttpReadData",
    "-i", "winhttp.dll!WinHttpQueryHeaders",
    "-i", "winhttp.dll!WinHttpAddRequestHeaders",
    "-i", "bcrypt.dll!BCryptCreateHash",
    "-i", "bcrypt.dll!BCryptHashData",
    "-i", "bcrypt.dll!BCryptFinishHash",
    "-i", "kernelbase.dll!CryptUnprotectData",
    "-i", "tcaddin.dll!*Auth*",
    "-i", "tcaddin.dll!*Token*",
    "-i", "tcaddin.dll!*Sign*",
    "-i", "tcaddin.dll!*Hmac*",
    "-o", $fridaLog
)
$fridaProc = Start-Process -FilePath $fridaTrace -ArgumentList $fridaArgs `
    -RedirectStandardOutput "$cap\frida.stdout" -RedirectStandardError "$cap\frida.stderr" `
    -WindowStyle Hidden -PassThru
Set-Content -LiteralPath "$cap\frida.pid" -Value $fridaProc.Id
Log "frida-trace started, pid=$($fridaProc.Id), log=$fridaLog" Green

Start-Sleep -Seconds 3
if ($fridaProc.HasExited) {
    Log "frida-trace exited immediately - check $cap\frida.stderr" Red
    Get-Content -LiteralPath "$cap\frida.stderr" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
}

Log "" Cyan
Log "=========================================" Cyan
Log "CAPTURE ACTIVE - $cap" Cyan
Log "=========================================" Cyan
Log "Now: trigger ONE AI feature in PowerPoint." Yellow
Log "When the response renders, run:" Yellow
Log "  $PSScriptRoot\stop_phase12_capture.ps1" Yellow
