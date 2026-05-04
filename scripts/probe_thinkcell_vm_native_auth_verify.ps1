<#
Windows VM native verification probe for the auth question.

Goal: replace inference with direct evidence. Run on the VM where we have
native PE tools, ETW, and the live process.

Probes (all native, no Frida/mitmproxy needed):

1. dumpbin /imports tcaddin.dll — definitive list of Windows APIs imported
   (confirms BCrypt, WinHTTP, DPAPI, CryptoAPI usage)
2. dumpbin /exports tcaddin.dll — what tcaddin actually exports
3. PE strings UTF-16LE proper extraction (PowerShell + native System.Text.Encoding.Unicode)
4. Live Get-NetTCPConnection -OwningProcess for POWERPNT.EXE
   (captures live remote IPs while PowerPoint is running)
5. WinHttp ETW provider trace for POWERPNT.EXE (5-second window)
   — captures HTTP URIs without needing mitmproxy
6. WinHttp HTTPS body inspection through bcrypt provider hooks
   (we can see if HMAC is called, with what algorithm, by tracing
   bcrypt!BCryptHashData via logman/perfview)
7. Search tcaddin.dll for JWT-format strings: '"alg":', '"typ":"JWT"',
   eyJhb (base64-encoded JWT header start)
8. Search for canonical-request signing format strings (date format,
   newline-separated headers, x-amz-* style headers)

All read-only. No interactive desktop required (except #5 needs PowerPoint
already loaded; if not present we skip).
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [string] $TcAddinDll = "C:\Program Files (x86)\think-cell\arm64\tcaddin.dll"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-vm-native-auth-verify/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        dumpbin_imports = $null
        dumpbin_exports = $null
        utf16_strings_grep = [ordered]@{}
        ascii_strings_grep = [ordered]@{}
        powerpnt = [ordered]@{}
        live_connections = @()
        winhttp_etw_events = @()
        jwt_evidence = [ordered]@{}
        canonical_signing_evidence = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}
function Add-Err {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

if (-not (Test-Path -LiteralPath $TcAddinDll)) {
    Add-Err -Result $result -Where "dll_missing" -Err $TcAddinDll
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}

# 1. dumpbin /imports — definitive imports
$dumpbin = (Get-Command dumpbin -ErrorAction SilentlyContinue)
if (-not $dumpbin) {
    # Try VS Build Tools default paths
    $candidates = @(
        "C:\Program Files (x86)\Microsoft Visual Studio\*\BuildTools\VC\Tools\MSVC\*\bin\Hostarm64\arm64\dumpbin.exe",
        "C:\Program Files\Microsoft Visual Studio\*\Community\VC\Tools\MSVC\*\bin\Hostarm64\arm64\dumpbin.exe",
        "C:\Program Files (x86)\Microsoft Visual Studio\*\Community\VC\Tools\MSVC\*\bin\Hostx64\x64\dumpbin.exe"
    )
    foreach ($c in $candidates) {
        $hit = Get-ChildItem -Path $c -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { $dumpbin = $hit; break }
    }
}
if ($dumpbin) {
    try {
        $imports = & $dumpbin.Source /IMPORTS $TcAddinDll 2>&1
        $result.dumpbin_imports = ($imports | Out-String)
    } catch { Add-Err -Result $result -Where "dumpbin_imports" -Err $_ }
    try {
        $exports = & $dumpbin.Source /EXPORTS $TcAddinDll 2>&1
        $result.dumpbin_exports = ($exports | Out-String)
    } catch { Add-Err -Result $result -Where "dumpbin_exports" -Err $_ }
} else {
    # Fallback: parse the import table ourselves via PE manipulation
    Add-Err -Result $result -Where "dumpbin" -Err "dumpbin.exe not found; using parsing fallback"
    try {
        Add-Type -TypeDefinition @"
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;

public static class PEParser {
    [StructLayout(LayoutKind.Sequential)]
    public struct IMAGE_DOS_HEADER { public ushort e_magic; public ushort e_cblp; public ushort e_cp; public ushort e_crlc; public ushort e_cparhdr; public ushort e_minalloc; public ushort e_maxalloc; public ushort e_ss; public ushort e_sp; public ushort e_csum; public ushort e_ip; public ushort e_cs; public ushort e_lfarlc; public ushort e_ovno; [MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)] public ushort[] e_res1; public ushort e_oemid; public ushort e_oeminfo; [MarshalAs(UnmanagedType.ByValArray, SizeConst = 10)] public ushort[] e_res2; public int e_lfanew; }

    public static List<string> ListImportedDlls(string path) {
        var result = new List<string>();
        var bytes = File.ReadAllBytes(path);
        if (bytes.Length < 0x40) return result;
        int peOff = BitConverter.ToInt32(bytes, 0x3c);
        // PE\0\0 signature
        if (peOff < 0 || peOff > bytes.Length - 24) return result;
        // FileHeader is at peOff+4, OptionalHeader at peOff+24
        ushort sizeOptHdr = BitConverter.ToUInt16(bytes, peOff + 20);
        int sectionsOff = peOff + 24 + sizeOptHdr;
        ushort numSections = BitConverter.ToUInt16(bytes, peOff + 6);
        // Optional header magic at peOff+24
        ushort magic = BitConverter.ToUInt16(bytes, peOff + 24);
        bool isPE32Plus = magic == 0x20b;
        // DataDirectory[1] = Import table — at offset peOff+24 + (96 for PE32, 112 for PE32+) + 1*8
        int importDirOff = peOff + 24 + (isPE32Plus ? 112 : 96) + 1*8;
        uint importVa = BitConverter.ToUInt32(bytes, importDirOff);
        uint importSize = BitConverter.ToUInt32(bytes, importDirOff + 4);
        if (importVa == 0) return result;

        // Find which section contains importVa
        Func<uint, int> rva2off = (rva) => {
            for (int i = 0; i < numSections; i++) {
                int s = sectionsOff + i*40;
                uint vSize = BitConverter.ToUInt32(bytes, s + 8);
                uint vAddr = BitConverter.ToUInt32(bytes, s + 12);
                uint rSize = BitConverter.ToUInt32(bytes, s + 16);
                uint rAddr = BitConverter.ToUInt32(bytes, s + 20);
                if (rva >= vAddr && rva < vAddr + Math.Max(vSize, rSize)) {
                    return (int)(rva - vAddr + rAddr);
                }
            }
            return -1;
        };

        int importOff = rva2off(importVa);
        if (importOff < 0) return result;
        // Walk IMAGE_IMPORT_DESCRIPTORs (20 bytes each, last is null)
        for (int i = 0; ; i++) {
            int desc = importOff + i*20;
            if (desc + 20 > bytes.Length) break;
            uint nameRva = BitConverter.ToUInt32(bytes, desc + 12);
            if (nameRva == 0) break;
            int nameOff = rva2off(nameRva);
            if (nameOff < 0) break;
            int nameLen = 0;
            while (nameOff + nameLen < bytes.Length && bytes[nameOff + nameLen] != 0) nameLen++;
            string name = Encoding.ASCII.GetString(bytes, nameOff, nameLen);
            result.Add(name);
        }
        return result;
    }
}
"@
        $imports = [PEParser]::ListImportedDlls($TcAddinDll)
        $result.dumpbin_imports = "[Fallback PE parser] Imported DLLs:`n" + ($imports -join "`n")
    } catch { Add-Err -Result $result -Where "pe_parser" -Err $_ }
}

# 2. UTF-16LE strings extraction in PowerShell (proper)
try {
    $bytes = [System.IO.File]::ReadAllBytes($TcAddinDll)
    $utf16 = [System.Text.Encoding]::Unicode.GetString($bytes)
    $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)

    $checks = @{
        # Verify the contested claims
        "PpAICoreURL" = "PpAICoreURL"
        "PpAICoreToken" = "PpAICoreToken"
        "app.prod.ai.think-cell.com/core/" = "app.prod.ai.think-cell.com/core/"
        "oauth.canto.com/oauth/" = "oauth.canto.com/oauth/"
        "api.gettyimages.com" = "api.gettyimages.com"
        "BCryptCreateHash" = "BCryptCreateHash"
        "BCryptHashData" = "BCryptHashData"
        "BCRYPT_SHA256_ALGORITHM" = "BCRYPT_SHA256_ALGORITHM"
        "BCRYPT_HMAC_FLAG" = "BCRYPT_ALG_HANDLE_HMAC_FLAG"
        "S:\tcaddin\PpAddIn" = "S:\tcaddin\PpAddIn"
        "messages_role_content" = '"messages":'

        # JWT tests
        "JWT_alg_field" = '"alg":'
        "JWT_typ_field" = '"typ":"JWT"'
        "JWT_kid_field" = '"kid":'
        "JWT_b64_header_eyJ" = "eyJ"
        "JWT_RS256" = "RS256"
        "JWT_HS256" = "HS256"
        "JWT_ES256" = "ES256"

        # Canonical-request signing
        "AWS_x_amz_date" = "x-amz-date"
        "Canonical_signed_headers" = "SignedHeaders"
        "Canonical_request_marker" = "Canonical"
        "AWS4_marker" = "AWS4"
        "Sha256_hex_marker" = "X-Content-Sha256"
        "X-TC-Date" = "X-TC-Date"
        "X-TC-Sig" = "X-TC-Sig"
        "X-TC-Token" = "X-TC-Token"
        "X-License-Key" = "X-License-Key"
        "X-Build" = "X-Build"
        "X-Tenant" = "X-Tenant"
    }

    foreach ($k in $checks.Keys) {
        $v = $checks[$k]
        $inAscii = $ascii.Contains($v)
        $inUtf16 = $utf16.Contains($v)
        $result.utf16_strings_grep[$k] = [ordered]@{
            needle = $v; in_ascii = $inAscii; in_utf16 = $inUtf16
        }
    }

    # Surrounding context for the things we WANT to look at deeper
    foreach ($needle in @("PpAICoreURL", "app.prod.ai.think-cell.com", "oauth.canto.com", "api.gettyimages.com", "BCryptCreateHash")) {
        $idx = $utf16.IndexOf($needle)
        if ($idx -lt 0) { $idx = $ascii.IndexOf($needle); $src = "ascii" } else { $src = "utf16" }
        if ($idx -ge 0) {
            $start = [Math]::Max(0, $idx - 200)
            $maxLen = if ($src -eq "ascii") { $ascii.Length } else { $utf16.Length }
            $endpos = [Math]::Min($maxLen, $idx + $needle.Length + 200)
            $ctx = if ($src -eq "ascii") { $ascii.Substring($start, $endpos - $start) } else { $utf16.Substring($start, $endpos - $start) }
            $clean = ($ctx -split '\x00+' | Where-Object { $_.Length -gt 4 }) -join ' | '
            $result.ascii_strings_grep["context_$needle"] = $clean.Substring(0, [Math]::Min(800, $clean.Length))
        }
    }
} catch { Add-Err -Result $result -Where "string_decode" -Err $_ }

# 3. POWERPNT process info (if running)
try {
    $pproc = Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pproc) {
        $result.powerpnt.pid = $pproc.Id
        $result.powerpnt.start_time = $pproc.StartTime.ToString("o")
        $result.powerpnt.module_count = $pproc.Modules.Count
        $tcLoaded = @($pproc.Modules | Where-Object { $_.ModuleName -match "(?i)tc|think" })
        $result.powerpnt.tc_modules = @($tcLoaded | ForEach-Object { [ordered]@{ name = $_.ModuleName; file = $_.FileName; base = ("0x" + $_.BaseAddress.ToInt64().ToString("X16")) } })

        # Live TCP connections of POWERPNT
        try {
            $conns = Get-NetTCPConnection -OwningProcess $pproc.Id -ErrorAction SilentlyContinue
            $result.live_connections = @($conns | ForEach-Object {
                $remote = $null; try { $remote = (Resolve-DnsName -Type PTR $_.RemoteAddress -ErrorAction SilentlyContinue).NameHost } catch {}
                [ordered]@{
                    state = [string]$_.State
                    local = "$($_.LocalAddress):$($_.LocalPort)"
                    remote = "$($_.RemoteAddress):$($_.RemotePort)"
                    remote_ptr = $remote
                }
            })
        } catch { Add-Err -Result $result -Where "powerpnt_conn" -Err $_ }
    } else {
        $result.powerpnt.running = $false
    }
} catch { Add-Err -Result $result -Where "powerpnt_proc" -Err $_ }

# 4. WinHttp ETW capture (5 sec snapshot if PowerPoint running) — best-effort
if ($pproc) {
    $etwLog = Join-Path $env:TEMP "tcw_winhttp_$(Get-Random).etl"
    try {
        # Microsoft-Windows-WinHttp provider GUID
        & logman create trace tcw_winhttp -p "{7d44233d-3055-4b9c-ba64-0d47ca40a232}" 0xffffffffffffffff 0xff -ets -o $etwLog -nb 16 16 -bs 1024 2>&1 | Out-Null
        Start-Sleep -Seconds 5
        & logman stop tcw_winhttp -ets 2>&1 | Out-Null
        # Convert ETL to text (best-effort)
        $textLog = "$etwLog.txt"
        & tracerpt $etwLog -o $textLog -of CSV -y 2>&1 | Out-Null
        if (Test-Path $textLog) {
            $tcEvents = Get-Content $textLog -ErrorAction SilentlyContinue | Where-Object { $_ -match "(?i)think-cell\.com|appcom|canto|gettyimages|unsplash|pexels|freepik|flaticon" } | Select-Object -First 50
            $result.winhttp_etw_events = @($tcEvents)
        }
        Remove-Item $etwLog, $textLog -ErrorAction SilentlyContinue
    } catch { Add-Err -Result $result -Where "winhttp_etw" -Err $_ }
}

# Verdict — compute from grep results
$confirmed = @($result.utf16_strings_grep.GetEnumerator() | Where-Object { $_.Value.in_ascii -or $_.Value.in_utf16 })
$denied = @($result.utf16_strings_grep.GetEnumerator() | Where-Object { -not ($_.Value.in_ascii -or $_.Value.in_utf16) })
$result.verdict.confirmed_strings = @($confirmed | ForEach-Object { $_.Key })
$result.verdict.denied_strings = @($denied | ForEach-Object { $_.Key })

# JWT verdict
$jwtMarkers = @("JWT_alg_field", "JWT_typ_field", "JWT_kid_field", "JWT_b64_header_eyJ", "JWT_RS256", "JWT_HS256", "JWT_ES256")
$jwtHits = @($jwtMarkers | Where-Object { $result.utf16_strings_grep.$_.in_ascii -or $result.utf16_strings_grep.$_.in_utf16 })
$result.verdict.jwt_evidence_count = $jwtHits.Count
$result.verdict.jwt_evidence_strings = $jwtHits
$result.verdict.jwt_likely = ($jwtHits.Count -ge 2)

# Canonical-request verdict
$crMarkers = @("AWS_x_amz_date", "Canonical_signed_headers", "Canonical_request_marker", "AWS4_marker", "X-TC-Date", "X-TC-Sig", "X-Content-Sha256")
$crHits = @($crMarkers | Where-Object { $result.utf16_strings_grep.$_.in_ascii -or $result.utf16_strings_grep.$_.in_utf16 })
$result.verdict.canonical_request_evidence_count = $crHits.Count
$result.verdict.canonical_request_likely = ($crHits.Count -ge 2)

# BCrypt verdict (already known true via ASCII strings)
$result.verdict.bcrypt_definitively_used = ($result.utf16_strings_grep.BCryptCreateHash.in_ascii -or $result.utf16_strings_grep.BCryptCreateHash.in_utf16)
$result.verdict.bcrypt_sha256_likely = ($result.utf16_strings_grep.BCRYPT_SHA256_ALGORITHM.in_ascii -or $result.utf16_strings_grep.BCRYPT_SHA256_ALGORITHM.in_utf16)
$result.verdict.bcrypt_hmac_flag = ($result.utf16_strings_grep.BCRYPT_HMAC_FLAG.in_ascii -or $result.utf16_strings_grep.BCRYPT_HMAC_FLAG.in_utf16)

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
