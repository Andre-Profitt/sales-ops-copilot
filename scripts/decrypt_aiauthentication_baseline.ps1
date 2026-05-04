#requires -Version 5.1
<#
DPAPI baseline - decrypts the current aiauthentication.bin and saves the parsed token.

This is a "before-capture" reference point. Run this NOW (before the capture session)
so we have the unredacted token shape on hand to compare against the
auth-refresh response we'll capture in Phase 12.

The token format (per MASTER_STATE) is:
  expires=<unix>&licensekeyid=<guid>&userhalfmonths=N&quota=N&hash=<HMAC>

Output: \Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\dpapi_baseline\<ts>\
  - aiauthentication.bin.copy        : the encrypted blob (for archival)
  - aiauthentication.decrypted.txt   : decrypted plaintext
  - aiauthentication.parsed.json     : parsed key/value pairs
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[dpapi] $m" -ForegroundColor $c }

$aiauth = "$env:APPDATA\think-cell\aiauthentication.bin"
if (-not (Test-Path -LiteralPath $aiauth)) {
    Log "aiauth missing: $aiauth" Red
    exit 1
}

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\dpapi_baseline\$ts"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Log "Output dir: $dest"

# 1. Save raw blob copy (archival)
Copy-Item -LiteralPath $aiauth -Destination "$dest\aiauthentication.bin.copy" -Force
$blobSize = (Get-Item -LiteralPath $aiauth).Length
Log "Saved encrypted blob copy ($blobSize bytes)"

# 2. Decrypt via DPAPI
Add-Type -AssemblyName System.Security
$ciphertext = [System.IO.File]::ReadAllBytes($aiauth)
$plaintext = [System.Security.Cryptography.ProtectedData]::Unprotect(
    $ciphertext,
    $null,
    [System.Security.Cryptography.DataProtectionScope]::CurrentUser
)
$decSize = $plaintext.Length
Log "Decrypted size: $decSize bytes" Green

# Decrypted blob structure (verified): [uint32 LE length][URL-encoded payload]
$lengthPrefix = [BitConverter]::ToUInt32($plaintext, 0)
$payloadBytes = $plaintext[4..($decSize - 1)]
Log "Length prefix (LE uint32): $lengthPrefix  payload bytes: $($payloadBytes.Length)"

$plainStr = [System.Text.Encoding]::UTF8.GetString($plaintext)
$payloadStr = [System.Text.Encoding]::UTF8.GetString($payloadBytes)
Set-Content -LiteralPath "$dest\aiauthentication.decrypted.txt" -Value $plainStr -Encoding UTF8
Set-Content -LiteralPath "$dest\aiauthentication.payload.txt" -Value $payloadStr -Encoding UTF8
Log "Payload (first 500 chars):" Green
Write-Host "  $($payloadStr.Substring(0, [Math]::Min(500, $payloadStr.Length)))"

# 3. Parse key=val pairs from the prefix-stripped payload
$parsed = [ordered]@{}
foreach ($pair in $payloadStr -split "&") {
    $kv = $pair -split "=", 2
    if ($kv.Count -eq 2) {
        $parsed[$kv[0]] = $kv[1]
    }
}
Log "Parsed fields: $($parsed.Keys -join ', ')" Green

# 4. Resolve expires timestamp
$expSummary = $null
if ($parsed.Contains("expires")) {
    try {
        $unixTs = [int64]$parsed["expires"]
        $when = [DateTimeOffset]::FromUnixTimeSeconds($unixTs)
        $expSummary = @{
            unix     = $unixTs
            iso      = $when.ToString("o")
            now_utc  = (Get-Date).ToUniversalTime().ToString("o")
            valid_for_hours = [Math]::Round(($when.UtcDateTime - (Get-Date).ToUniversalTime()).TotalHours, 2)
        }
        Log "Token valid for $($expSummary.valid_for_hours) more hours (expires $($expSummary.iso))" Green
    } catch {
        $expSummary = @{ raw = $parsed["expires"]; parse_error = $_.Exception.Message }
    }
}

# 5. Hash field shape
$hashShape = $null
if ($parsed.Contains("hash")) {
    $h = $parsed["hash"]
    $hashShape = @{
        length        = $h.Length
        looks_hex     = ($h -match "^[0-9a-fA-F]+$")
        looks_base64  = ($h -match "^[A-Za-z0-9+/=]+$")
        sha256_size_hex_64    = ($h.Length -eq 64)
        sha256_size_b64_44    = ($h.Length -eq 44 -or $h.Length -eq 43)
    }
}

# 6. Persist parsed JSON
$out = [ordered]@{
    timestamp_utc        = (Get-Date).ToUniversalTime().ToString("o")
    source_file          = $aiauth
    encrypted_size_bytes = $blobSize
    decrypted_size_bytes = $decSize
    blob_structure       = "uint32_le_length_prefix + url_encoded_payload"
    length_prefix        = $lengthPrefix
    payload_size_bytes   = $payloadBytes.Length
    field_names          = $parsed.Keys
    fields               = $parsed
    expires_summary      = $expSummary
    hash_shape           = $hashShape
}
$out | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$dest\aiauthentication.parsed.json" -Encoding UTF8
Log "Wrote $dest\aiauthentication.parsed.json" Green

Log "" Cyan
Log "=== DPAPI baseline complete ===" Cyan
Log "Pre-capture reference is now on Mac. Compare this to the post-capture" Cyan
Log "auth-refresh response field-by-field." Cyan
