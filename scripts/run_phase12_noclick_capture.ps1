<#
Phase 12 — no-click capture, runs as a scheduled task in Session 1.

Triggers the auth flow via PowerPoint COLD START with a deleted token.
PowerPoint launching with think-cell loaded auto-validates/refreshes the
token at startup — that fires the auth handshake to aiauthentication.appcom
+ the BCrypt-CNG HMAC computations + the WinHttp send/receive sequence.

We capture all of that without needing a UI click.

Limitations vs. the click-based capture:
- We get the auth-exchange flow + HMAC moments (Phase 12 observables #2 + #4)
- We DO NOT get the actual /core/ AI body shape (#1 + #3) — that needs the
  AI feature firing. But the HMAC scheme is identical, so once the auth
  flow is decoded we can construct AI requests ourselves.

Output marker: $env:USERPROFILE\tc_phase12_capture_done.json
This script is run via scheduled task; SSH polls for the marker.
#>
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$cap = "$env:USERPROFILE\tc_auth\$ts"
New-Item -ItemType Directory -Path $cap -Force | Out-Null

$marker = "$env:USERPROFILE\tc_phase12_capture_done.json"
$markerStart = "$env:USERPROFILE\tc_phase12_capture_started.json"

$state = [ordered]@{
    schema = "tc-phase12-noclick/v1"
    started_utc = [DateTime]::UtcNow.ToString("o")
    capture_dir = $cap
    pid_self = $PID
    session_id = (Get-Process -PID $PID).SessionId
    interactive = [System.Environment]::UserInteractive
    steps = @()
    errors = @()
}
$state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $markerStart -Force

function Step($label, $action) {
    $entry = [ordered]@{ step = $label; started_utc = [DateTime]::UtcNow.ToString("o"); ok = $true; note = "" }
    try {
        $r = & $action
        if ($r) { $entry.note = ($r -join " | ").Substring(0, [Math]::Min(200, ($r -join " | ").Length)) }
    } catch {
        $entry.ok = $false
        $entry.note = $_.Exception.Message.Substring(0, [Math]::Min(200, $_.Exception.Message.Length))
        $state.errors += [ordered]@{ step = $label; message = $_.Exception.Message }
    }
    $entry.ended_utc = [DateTime]::UtcNow.ToString("o")
    $state.steps += $entry
}

# ----- 1. Stop any PowerPoint (we want a true cold start) -----
Step "stop_powerpoint" {
    Get-Process POWERPNT -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

# ----- 2. Backup + delete aiauthentication.bin -----
$tcDir = "$env:APPDATA\think-cell"
$aiauth = "$tcDir\aiauthentication.bin"
$bak = "$tcDir\aiauthentication.bin.bak"
Step "backup_delete_token" {
    if (Test-Path -LiteralPath $aiauth) {
        Copy-Item -LiteralPath $aiauth -Destination $bak -Force
        Remove-Item -LiteralPath $aiauth -Force
        "backed up $aiauth -> $bak"
    } else {
        "aiauthentication.bin not present"
    }
}

# ----- 3. Resolve mitmdump + frida-trace from x64 Python install -----
$mitmdump = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe"
$fridaTrace = "$env:APPDATA\Python\Python313\Scripts\frida-trace.exe"

# ----- 4. Set system proxy to mitm -----
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Step "set_system_proxy" {
    $bak = @{}
    foreach ($p in @("ProxyEnable", "ProxyServer", "ProxyOverride")) {
        $bak[$p] = (Get-ItemProperty -Path $reg -Name $p -ErrorAction SilentlyContinue).$p
    }
    $bak | ConvertTo-Json | Set-Content -LiteralPath "$cap\proxy_backup.json" -Force
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
    Set-ItemProperty -Path $reg -Name ProxyServer -Value "127.0.0.1:8888"
    Set-ItemProperty -Path $reg -Name ProxyOverride -Value "<-loopback>" -ErrorAction SilentlyContinue
    & netsh winhttp set proxy "127.0.0.1:8888" 2>&1 | Out-Null
    "proxy set to 127.0.0.1:8888"
}

# ----- 5. Start mitmdump in background -----
$mitmHar = "$cap\mitm.har"
$mitmFlow = "$cap\mitm.flow"
$mitmLog = "$cap\mitm.log"
$mitmFilter = "~h (aiauthentication|cdnauthentication|ai\.appcom|app\.prod\.ai|prod\.ai|usage\.appcom)\.think-cell\.com"
Step "start_mitmdump" {
    if (-not (Test-Path -LiteralPath $mitmdump)) { throw "missing mitmdump.exe at $mitmdump" }
    # NOTE: --view-filter is a mitmweb option; mitmdump doesn't have it.
    # We capture all traffic and filter post-hoc on the Mac side.
    $mitmArgs = @(
        "-p", "8888",
        "--listen-host", "127.0.0.1",
        "--set", "hardump=$mitmHar",
        "-w", $mitmFlow
    )
    $proc = Start-Process -FilePath $mitmdump -ArgumentList $mitmArgs `
        -RedirectStandardOutput $mitmLog -RedirectStandardError "$mitmLog.err" `
        -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content -LiteralPath "$cap\mitm.pid" -Force
    Start-Sleep -Seconds 2
    "mitmdump pid=$($proc.Id)"
}

# ----- 6. Cold-launch PowerPoint (in Session 1 — we ARE in Session 1 because scheduled-task /it) -----
$pptExe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Step "launch_powerpoint" {
    if (-not (Test-Path -LiteralPath $pptExe)) { throw "POWERPNT.EXE not found at $pptExe" }
    $proc = Start-Process -FilePath $pptExe -ArgumentList "/N" -PassThru
    $proc.Id | Set-Content -LiteralPath "$cap\powerpnt.pid" -Force
    "POWERPNT pid=$($proc.Id)"
}

# Wait for POWERPNT to be ready before attaching Frida
Start-Sleep -Seconds 5
$ppPid = (Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1).Id
if (-not $ppPid) {
    $state.errors += [ordered]@{ step = "wait_for_powerpnt"; message = "POWERPNT not detected after 5s" }
}

# ----- 7. Attach frida-trace -----
$fridaLog = "$cap\frida.log"
Step "attach_frida" {
    if (-not (Test-Path -LiteralPath $fridaTrace)) { throw "missing frida-trace.exe at $fridaTrace" }
    if (-not $ppPid) { throw "no POWERPNT pid" }
    $fArgs = @(
        "-p", "$ppPid",
        "-i", "winhttp.dll!WinHttpSendRequest",
        "-i", "winhttp.dll!WinHttpWriteData",
        "-i", "winhttp.dll!WinHttpReceiveResponse",
        "-i", "winhttp.dll!WinHttpReadData",
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
    # CWD must be writable: frida-trace creates __handlers__/ in cwd. Default
    # CWD for scheduled tasks is C:\Windows\system32 which is read-only for
    # non-admin users. Use the capture dir.
    $proc = Start-Process -FilePath $fridaTrace -ArgumentList $fArgs `
        -WorkingDirectory $cap `
        -RedirectStandardOutput "$cap\frida_stdout.log" -RedirectStandardError "$cap\frida_stderr.log" `
        -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content -LiteralPath "$cap\frida.pid" -Force
    Start-Sleep -Seconds 2
    "frida-trace pid=$($proc.Id)"
}

# ----- 8. Wait 60s for cold-start auth flow to fire + be captured -----
Step "wait_for_capture" {
    Start-Sleep -Seconds 60
    "60s elapsed"
}

# ----- 9. Snapshot the new aiauthentication.bin (if think-cell rewrote it) -----
Step "snapshot_token" {
    if (Test-Path -LiteralPath $aiauth) {
        Copy-Item -LiteralPath $aiauth -Destination "$cap\aiauthentication.bin.captured" -Force
        $sz = (Get-Item -LiteralPath "$cap\aiauthentication.bin.captured").Length
        "captured token size: $sz bytes"
    } else {
        "no token rewritten by think-cell yet"
    }
}

# ----- 10. Stop frida + mitm -----
Step "stop_frida" {
    $fpid = Get-Content -LiteralPath "$cap\frida.pid" -ErrorAction SilentlyContinue
    if ($fpid) { Stop-Process -Id ([int]$fpid) -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    "stopped frida pid=$fpid"
}
Step "stop_mitmdump" {
    $mpid = Get-Content -LiteralPath "$cap\mitm.pid" -ErrorAction SilentlyContinue
    if ($mpid) { Stop-Process -Id ([int]$mpid) -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    "stopped mitmdump pid=$mpid"
}

# ----- 11. Reset proxy + restore token -----
Step "reset_proxy" {
    & netsh winhttp reset proxy 2>&1 | Out-Null
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0
    "proxy reset"
}
Step "restore_token" {
    if (Test-Path -LiteralPath $bak) {
        Copy-Item -LiteralPath $bak -Destination $aiauth -Force
        "restored aiauthentication.bin from $bak"
    }
}

# ----- 12. Write completion marker -----
$state.ended_utc = [DateTime]::UtcNow.ToString("o")
$state.harSize = if (Test-Path -LiteralPath $mitmHar) { (Get-Item -LiteralPath $mitmHar).Length } else { 0 }
$state.fridaLogSize = if (Test-Path -LiteralPath $fridaLog) { (Get-Item -LiteralPath $fridaLog).Length } else { 0 }
$state.captured_token = (Test-Path -LiteralPath "$cap\aiauthentication.bin.captured")
$state.flowSize = if (Test-Path -LiteralPath $mitmFlow) { (Get-Item -LiteralPath $mitmFlow).Length } else { 0 }
$state.captureFiles = (Get-ChildItem -LiteralPath $cap -ErrorAction SilentlyContinue | ForEach-Object { @{ name = $_.Name; size = $_.Length } })
$state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $marker -Force
