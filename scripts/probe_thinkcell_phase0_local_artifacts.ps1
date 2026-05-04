<#
Phase 0b — full deep-read of local artifacts on the VM.

Reads (and Mac-side ferries via OutputPath):
- C:\Users\test\AppData\Roaming\think-cell\settings.xml (full 58KB)
- C:\Users\test\AppData\Roaming\think-cell\aiauthentication.bin (bytes + magic)
- C:\Users\test\AppData\Local\think-cell\settings.xml
- C:\Users\test\AppData\Local\think-cell\POWERPNT.officeUI
- C:\Users\test\AppData\Local\think-cell\tcupdate_log.log (full 73KB)
- Filesystem listing of any other think-cell-related paths

Static analysis only. No runtime calls.
#>
[CmdletBinding()]
param([string] $OutputPath)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-phase0-local-artifacts/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        files = @()
        errors = @()
    }
}
function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.user = $env:USERNAME

$paths = @(
    "$env:APPDATA\think-cell\settings.xml",
    "$env:APPDATA\think-cell\aiauthentication.bin",
    "$env:LOCALAPPDATA\think-cell\settings.xml",
    "$env:LOCALAPPDATA\think-cell\POWERPNT.officeUI",
    "$env:LOCALAPPDATA\think-cell\tcupdate_log.log"
)

foreach ($p in $paths) {
    $entry = [ordered]@{
        path = $p
        exists = (Test-Path -LiteralPath $p)
    }
    if (-not $entry.exists) { $result.files += $entry; continue }
    try {
        $f = Get-Item -LiteralPath $p
        $entry.size = $f.Length
        $entry.last_write_utc = $f.LastWriteTimeUtc.ToString("o")
        $bytes = [System.IO.File]::ReadAllBytes($p)
        $entry.sha256 = [System.BitConverter]::ToString(
            (New-Object System.Security.Cryptography.SHA256Managed).ComputeHash($bytes)
        ).Replace("-", "").ToLowerInvariant()
        $entry.head_hex = (($bytes[0..([Math]::Min(63, $bytes.Length-1))] | ForEach-Object { $_.ToString("X2") }) -join "")
        # Try UTF-8 decode for textual content
        try {
            $entry.text = [System.Text.Encoding]::UTF8.GetString($bytes)
            $printable = ($entry.text.ToCharArray() | Where-Object { [char]::IsControl($_) -eq $false -or $_ -eq "`n" -or $_ -eq "`r" -or $_ -eq "`t" }).Count
            if ($entry.text.Length -gt 0 -and ($printable / $entry.text.Length) -gt 0.85) {
                $entry.is_text = $true
            } else {
                $entry.text = $null
                $entry.is_text = $false
            }
        } catch { $entry.text = $null; $entry.is_text = $false }
        # Magic-byte sniff
        $magic = $null
        if ($bytes.Length -ge 8) {
            if ($bytes[0] -eq 0x01 -and $bytes[1] -eq 0x00 -and $bytes[2] -eq 0x00 -and $bytes[3] -eq 0x00 -and $bytes[4] -eq 0xD0 -and $bytes[5] -eq 0x8C) {
                $magic = "DPAPI_BLOB"
            } elseif ($bytes[0] -eq 0x65 -and $bytes[1] -eq 0x79 -and $bytes[2] -eq 0x4A) {
                $magic = "JWT (eyJ)"
            } elseif ($bytes[0] -eq 0x50 -and $bytes[1] -eq 0x4B) {
                $magic = "ZIP"
            } elseif ($bytes[0] -eq 0xD0 -and $bytes[1] -eq 0xCF -and $bytes[2] -eq 0x11 -and $bytes[3] -eq 0xE0) {
                $magic = "CFB"
            } elseif ($bytes[0] -eq 0x78 -and ($bytes[1] -eq 0x9C -or $bytes[1] -eq 0xDA)) {
                $magic = "zlib"
            } elseif ($bytes[0] -eq 0x1F -and $bytes[1] -eq 0x8B) {
                $magic = "gzip"
            } elseif ($bytes[0] -eq 0x3C -and $bytes[1] -eq 0x3F -and $bytes[2] -eq 0x78 -and $bytes[3] -eq 0x6D) {
                $magic = "XML (<?xm)"
            } elseif ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
                $magic = "UTF-8 BOM"
            }
        }
        $entry.magic_byte_format = $magic
    } catch {
        Add-ErrorRow -Result $result -Where "read:$p" -Err $_
    }
    $result.files += $entry
}

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
