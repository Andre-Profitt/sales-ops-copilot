#requires -Version 5.1
<#
Phase 12 setup - delta: install mitmproxy portable + generate CA + trust in user root.

Why this exists:
- pip install mitmproxy fails on Windows ARM64 (no prebuilt wheels for cryptography /
  mitmproxy-rs / aioquic / Brotli; building from source needs MSVC link.exe).
- mitmproxy publishes a portable x86_64 zip; Windows on ARM64 runs x64 transparently
  via emulation.
- This is interactive-desktop-only, AI-feature-capture scope. Personal VM.
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[mitm-setup] $m" -ForegroundColor $c }

$mitmVer = "12.2.2"
$zipUrl  = "https://downloads.mitmproxy.org/$mitmVer/mitmproxy-$mitmVer-windows-x86_64.zip"
$instDir = "$env:LOCALAPPDATA\mitmproxy"
$zipPath = "$env:TEMP\mitmproxy-$mitmVer.zip"

# 1. Download portable zip
if (-not (Test-Path "$instDir\mitmdump.exe")) {
    Log "Downloading $zipUrl"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    New-Item -ItemType Directory -Path $instDir -Force | Out-Null
    Log "Extracting to $instDir"
    Expand-Archive -Path $zipPath -DestinationPath $instDir -Force
    Remove-Item $zipPath -Force
} else {
    Log "mitmdump.exe already present in $instDir" Green
}

# 2. Verify binary
$mitmdump = "$instDir\mitmdump.exe"
if (-not (Test-Path $mitmdump)) {
    throw "mitmdump.exe not found after extract; contents: $(Get-ChildItem $instDir | Select-Object -ExpandProperty Name)"
}
$mitmdumpVer = (& $mitmdump --version 2>&1 | Select-String -Pattern "Mitmproxy:" | Select-Object -First 1).Line
Log "mitmdump version: $mitmdumpVer" Green

# 3. Generate CA by running mitmdump briefly (exits on its own after CA gen)
$caDir  = "$env:USERPROFILE\.mitmproxy"
$caPath = "$caDir\mitmproxy-ca-cert.cer"
if (-not (Test-Path $caPath)) {
    Log "Generating CA via mitmdump first-run"
    $proc = Start-Process -FilePath $mitmdump -ArgumentList "-p","18888","--listen-host","127.0.0.1" -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and -not (Test-Path $caPath)) {
        Start-Sleep -Milliseconds 500
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if (-not (Test-Path $caPath)) {
    throw "CA cert was not generated at $caPath"
}
Log "CA exists: $caPath" Green

# 4. Trust CA in CurrentUser\Root (no admin required)
$existing = Get-ChildItem -Path Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
            Where-Object { $_.Subject -match "mitmproxy" }
if ($existing) {
    Log "CA already trusted in CurrentUser\Root: $($existing.Subject)" Green
} else {
    Log "Adding CA to CurrentUser\Root via certutil"
    & certutil -user -addstore -f "Root" $caPath | Out-Null
    $verify = Get-ChildItem -Path Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
              Where-Object { $_.Subject -match "mitmproxy" }
    if (-not $verify) {
        throw "certutil reported success but cert not found in CurrentUser\Root"
    }
    Log "CA trusted: $($verify.Subject)" Green
}

# 5. Final state report
$state = [ordered]@{
    mitmdump_path        = $mitmdump
    mitmdump_version     = $mitmdumpVer
    ca_cert_path         = $caPath
    ca_cert_exists       = (Test-Path $caPath)
    ca_trusted_user_root = $true
    zip_url              = $zipUrl
}
$state | ConvertTo-Json -Depth 4
