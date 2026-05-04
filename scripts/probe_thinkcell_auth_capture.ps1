<#
Phase 1 — focused auth-capture probe for think-cell.

Runs three captures in parallel against POWERPNT.EXE while you drive a
single AI-feature use:

  1. Frida hooks on BCrypt {OpenAlgorithmProvider, CreateHash, HashData,
     FinishHash} — captures the actual bytes being HMAC'd + the resulting
     hash. This is the load-bearing capture: the canonical-string format
     for the auth signature comes out of here.

  2. Frida hooks on WinHttp {AddRequestHeaders, SendRequest, WriteData} —
     captures pre-TLS HTTP request headers + bodies. Lets you correlate
     "this BCryptHashData call produced these bytes" with "that same byte
     string appears in this Authorization header at this URL."

  3. CryptUnprotectData on aiauthentication.bin — dumps the DPAPI
     plaintext so we know what's actually inside the token.

Read-only against the running PowerPoint process. Writes JSON outputs to
the path you supply. No network, no registry mutation, no file writes
outside the output dir.

Pre-conditions:
  - frida-tools installed (use scripts/setup_phase1_capture_env.ps1 first)
  - PowerPoint NOT running yet (we attach to it on launch)
  - Defender ASR rule for KB0233 disabled or excluded for tcaddin.dll —
    otherwise the binary may be deleted mid-capture
  - %APPDATA%\think-cell\aiauthentication.bin exists (run think-cell at
    least once first)

Usage:
  .\probe_thinkcell_auth_capture.ps1 -OutputDir "C:\tcauth-capture\<TS>"
                                     -DurationSeconds 180

After it runs, drive PowerPoint manually:
  1. Launch PowerPoint
  2. Wait ~5s for token validation
  3. Invoke ONE AI feature (e.g., natural-language chart suggestion)
  4. Wait for completion
  5. Optionally trigger one stock-image search
  6. Quit PowerPoint or wait for the duration timer to elapse

The output dir will contain:
  bcrypt_trace.jsonl    — every BCrypt call with input/output bytes (hex)
  winhttp_trace.jsonl   — every WinHttp call with headers + bodies
  dpapi_plaintext.bin   — the decrypted aiauthentication.bin payload
  dpapi_plaintext.txt   — same as text if it's printable
  capture_meta.json     — start/end timestamps + machine info
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,

    [int] $DurationSeconds = 180,

    [string] $TargetProcess = "POWERPNT.EXE"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Log { param($m) Write-Host "[auth-capture] $m" }

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$meta = [ordered]@{
    schema = "simcorp-thinkcell-auth-capture/v1"
    started_utc = [DateTime]::UtcNow.ToString("o")
    machine = [ordered]@{
        host = $env:COMPUTERNAME
        user = $env:USERNAME
        os = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
    }
    target_process = $TargetProcess
    duration_seconds = $DurationSeconds
    output_dir = $OutputDir
}

# ---------- 1. Decrypt aiauthentication.bin via DPAPI ----------
Log "Decrypting aiauthentication.bin"
$blobPath = Join-Path $env:APPDATA "think-cell\aiauthentication.bin"
if (-not (Test-Path -LiteralPath $blobPath)) {
    Log "WARNING: $blobPath not found — DPAPI capture skipped"
    $meta.dpapi = [ordered]@{ status = "missing_blob"; path = $blobPath }
} else {
    try {
        Add-Type -AssemblyName System.Security
        $cipher = [System.IO.File]::ReadAllBytes($blobPath)
        $plain = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $cipher, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        $plainBin = Join-Path $OutputDir "dpapi_plaintext.bin"
        [System.IO.File]::WriteAllBytes($plainBin, $plain)
        # If printable, also drop a .txt
        $isText = ($plain | ForEach-Object { ($_ -ge 0x20 -and $_ -lt 0x7f) -or $_ -in 9,10,13 }) -notcontains $false
        if ($isText) {
            $plainTxt = Join-Path $OutputDir "dpapi_plaintext.txt"
            [System.IO.File]::WriteAllText($plainTxt, [System.Text.Encoding]::ASCII.GetString($plain))
        }
        $meta.dpapi = [ordered]@{
            status = "ok"
            blob_size = $cipher.Length
            plaintext_size = $plain.Length
            plaintext_is_printable = $isText
        }
        Log "DPAPI plaintext: $($plain.Length) bytes (printable=$isText)"
    } catch {
        $meta.dpapi = [ordered]@{ status = "error"; message = $_.Exception.Message }
        Log "DPAPI decrypt failed: $($_.Exception.Message)"
    }
}

# ---------- 2. Generate Frida JS for BCrypt + WinHttp hooks ----------
$fridaScript = Join-Path $OutputDir "frida_hooks.js"
$bcryptOut = Join-Path $OutputDir "bcrypt_trace.jsonl"
$winhttpOut = Join-Path $OutputDir "winhttp_trace.jsonl"

# Escape paths for JS string literals (forward slashes work on Windows too)
$bcryptOutJs = ($bcryptOut -replace '\\', '/')
$winhttpOutJs = ($winhttpOut -replace '\\', '/')

$jsContent = @"
'use strict';

const fs = new File('$bcryptOutJs', 'a');
const fwh = new File('$winhttpOutJs', 'a');

function hex(ptr, len) {
  if (len <= 0 || ptr.isNull()) return '';
  try { return ptr.readByteArray(len).hexEncode(); } catch (e) { return '<unreadable>'; }
}

function writeJson(handle, obj) {
  try { handle.write(JSON.stringify(obj) + '\n'); handle.flush(); } catch (e) {}
}

// ---------- BCrypt hooks ----------
const bcrypt = Module.load('bcrypt.dll');

const fnHashData = bcrypt.getExportByName('BCryptHashData');
Interceptor.attach(fnHashData, {
  onEnter(args) {
    this.handle = args[0];
    this.input = args[1];
    this.cb = args[2].toInt32();
  },
  onLeave(ret) {
    writeJson(fs, {
      fn: 'BCryptHashData',
      ts: Date.now(),
      handle: this.handle.toString(),
      input_hex: hex(this.input, this.cb),
      cb: this.cb,
      ret: ret.toInt32(),
    });
  },
});

const fnFinishHash = bcrypt.getExportByName('BCryptFinishHash');
Interceptor.attach(fnFinishHash, {
  onEnter(args) {
    this.handle = args[0];
    this.output = args[1];
    this.cb = args[2].toInt32();
  },
  onLeave(ret) {
    writeJson(fs, {
      fn: 'BCryptFinishHash',
      ts: Date.now(),
      handle: this.handle.toString(),
      output_hex: hex(this.output, this.cb),
      cb: this.cb,
      ret: ret.toInt32(),
    });
  },
});

const fnCreateHash = bcrypt.getExportByName('BCryptCreateHash');
Interceptor.attach(fnCreateHash, {
  onEnter(args) {
    this.alg = args[0];
    this.handleOut = args[1];
    this.secret = args[3];
    this.cbSecret = args[4].toInt32();
    this.flags = args[6].toInt32();
  },
  onLeave(ret) {
    let handleStr = '';
    try { handleStr = this.handleOut.readPointer().toString(); } catch (e) {}
    writeJson(fs, {
      fn: 'BCryptCreateHash',
      ts: Date.now(),
      alg_handle: this.alg.toString(),
      hash_handle: handleStr,
      secret_hex: hex(this.secret, this.cbSecret),
      cb_secret: this.cbSecret,
      flags: this.flags,
      flag_hmac: (this.flags & 1) !== 0,  // BCRYPT_ALG_HANDLE_HMAC_FLAG = 0x00000001? confirm
      ret: ret.toInt32(),
    });
  },
});

const fnOpenAlg = bcrypt.getExportByName('BCryptOpenAlgorithmProvider');
Interceptor.attach(fnOpenAlg, {
  onEnter(args) {
    this.handleOut = args[0];
    try { this.algId = args[1].readUtf16String(); } catch (e) { this.algId = '<?>'; }
    this.flags = args[3].toInt32();
  },
  onLeave(ret) {
    let handleStr = '';
    try { handleStr = this.handleOut.readPointer().toString(); } catch (e) {}
    writeJson(fs, {
      fn: 'BCryptOpenAlgorithmProvider',
      ts: Date.now(),
      alg_id: this.algId,
      handle: handleStr,
      flags: this.flags,
      ret: ret.toInt32(),
    });
  },
});

// ---------- WinHttp hooks ----------
const winhttp = Module.load('winhttp.dll');

const fnSendRequest = winhttp.getExportByName('WinHttpSendRequest');
Interceptor.attach(fnSendRequest, {
  onEnter(args) {
    let headers = '';
    try { headers = args[1].readUtf16String(); } catch (e) {}
    const cbOptional = args[5].toInt32();
    const optionalHex = cbOptional > 0 ? hex(args[4], cbOptional) : '';
    writeJson(fwh, {
      fn: 'WinHttpSendRequest',
      ts: Date.now(),
      handle: args[0].toString(),
      headers: headers,
      optional_body_hex: optionalHex,
      cb_optional: cbOptional,
      cb_total: args[6].toInt32(),
    });
  },
});

const fnAddHeaders = winhttp.getExportByName('WinHttpAddRequestHeaders');
Interceptor.attach(fnAddHeaders, {
  onEnter(args) {
    let headers = '';
    try { headers = args[1].readUtf16String(); } catch (e) {}
    writeJson(fwh, {
      fn: 'WinHttpAddRequestHeaders',
      ts: Date.now(),
      handle: args[0].toString(),
      headers: headers,
      cb: args[2].toInt32(),
      modifiers: args[3].toInt32(),
    });
  },
});

const fnWriteData = winhttp.getExportByName('WinHttpWriteData');
Interceptor.attach(fnWriteData, {
  onEnter(args) {
    const cb = args[2].toInt32();
    writeJson(fwh, {
      fn: 'WinHttpWriteData',
      ts: Date.now(),
      handle: args[0].toString(),
      body_hex: hex(args[1], Math.min(cb, 65536)),
      cb: cb,
    });
  },
});

const fnOpenRequest = winhttp.getExportByName('WinHttpOpenRequest');
Interceptor.attach(fnOpenRequest, {
  onEnter(args) {
    let verb = '';
    let path = '';
    try { verb = args[1].readUtf16String(); } catch (e) {}
    try { path = args[2].readUtf16String(); } catch (e) {}
    writeJson(fwh, {
      fn: 'WinHttpOpenRequest',
      ts: Date.now(),
      conn_handle: args[0].toString(),
      verb: verb,
      path: path,
      flags: args[6].toInt32(),
    });
  },
});

const fnConnect = winhttp.getExportByName('WinHttpConnect');
Interceptor.attach(fnConnect, {
  onEnter(args) {
    let server = '';
    try { server = args[1].readUtf16String(); } catch (e) {}
    writeJson(fwh, {
      fn: 'WinHttpConnect',
      ts: Date.now(),
      session: args[0].toString(),
      server: server,
      port: args[2].toInt32(),
    });
  },
});

console.log('[auth-capture] hooks installed');
"@

[System.IO.File]::WriteAllText($fridaScript, $jsContent, [System.Text.Encoding]::UTF8)
Log "Wrote Frida script: $fridaScript"

# ---------- 3. Wait for target process, attach, run for duration ----------
Log "Waiting for $TargetProcess to start (timeout 120s)"
$proc = $null
$deadline = (Get-Date).AddSeconds(120)
while ($null -eq $proc -and (Get-Date) -lt $deadline) {
    $proc = Get-Process -Name ($TargetProcess -replace '\.exe$','') -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $proc) {
    Log "Target process did not start within 120s. Aborting."
    $meta.frida = [ordered]@{ status = "no_target"; message = "process not found" }
    $meta.ended_utc = [DateTime]::UtcNow.ToString("o")
    $meta | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutputDir "capture_meta.json") -Encoding UTF8
    exit 1
}
Log "Attaching Frida to PID $($proc.Id)"

$fridaArgs = @("-l", "`"$fridaScript`"", "-p", "$($proc.Id)", "-q")
$fridaProc = Start-Process -FilePath "frida" -ArgumentList $fridaArgs `
    -RedirectStandardOutput (Join-Path $OutputDir "frida_stdout.log") `
    -RedirectStandardError (Join-Path $OutputDir "frida_stderr.log") `
    -PassThru -NoNewWindow

Log "Capturing for $DurationSeconds seconds. Drive PowerPoint NOW: invoke ONE AI feature, then wait."
Start-Sleep -Seconds $DurationSeconds

Log "Stopping Frida"
try { Stop-Process -Id $fridaProc.Id -Force -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Seconds 2

# ---------- 4. Final meta ----------
$meta.frida = [ordered]@{
    status = "ok"
    target_pid = $proc.Id
    target_image = $proc.Path
    bcrypt_trace = $bcryptOut
    winhttp_trace = $winhttpOut
    bcrypt_lines = (Get-Content -LiteralPath $bcryptOut -ErrorAction SilentlyContinue | Measure-Object).Count
    winhttp_lines = (Get-Content -LiteralPath $winhttpOut -ErrorAction SilentlyContinue | Measure-Object).Count
}
$meta.ended_utc = [DateTime]::UtcNow.ToString("o")
$metaPath = Join-Path $OutputDir "capture_meta.json"
$meta | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $metaPath -Encoding UTF8
Log "Done. Captures at $OutputDir"
Log "  bcrypt: $($meta.frida.bcrypt_lines) lines"
Log "  winhttp: $($meta.frida.winhttp_lines) lines"
Log "  meta: $metaPath"
