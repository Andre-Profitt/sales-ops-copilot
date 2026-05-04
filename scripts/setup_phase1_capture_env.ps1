<#
Phase 1 — install Frida + mitmproxy + cert trust on the Windows VM.

One-time setup. Idempotent. Uses winget where possible.
#>
[CmdletBinding()]
param(
    [string] $MitmPort = "8888",
    [switch] $SkipCert,
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Log { param($m) Write-Host "[phase1-setup] $m" }

# Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Log "Installing Python via winget"
    winget install -e --id Python.Python.3.13 --silent
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Get-Command python -ErrorAction SilentlyContinue
}
Log "python: $($py.Source)"

# Frida
Log "Installing frida-tools"
& $py.Source -m pip install --upgrade pip frida-tools 2>&1 | Where-Object { $_ -notmatch '^\s*$' } | Select-Object -First 20

# mitmproxy
Log "Installing mitmproxy"
& $py.Source -m pip install --upgrade mitmproxy 2>&1 | Where-Object { $_ -notmatch '^\s*$' } | Select-Object -First 20

# Generate mitmproxy CA cert
$mitmDir = Join-Path $env:USERPROFILE ".mitmproxy"
if (-not (Test-Path $mitmDir) -or $Force) {
    Log "Generating mitmproxy CA cert (will run mitmdump briefly)"
    $proc = Start-Process -FilePath "$($py.Source)" -ArgumentList "-m mitmproxy.tools.dump", "-s '/dev/null'" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

# Trust mitmproxy CA in Windows root store (requires admin)
if (-not $SkipCert) {
    $caPath = Join-Path $mitmDir "mitmproxy-ca-cert.cer"
    if (Test-Path $caPath) {
        Log "Trusting mitmproxy CA at $caPath (requires admin)"
        try {
            certutil -addstore -f "Root" $caPath
            Log "Cert trusted in user/local Root store"
        } catch {
            Log "WARN: certutil failed; install manually: certutil -addstore -f Root '$caPath'"
        }
    } else {
        Log "WARN: $caPath not found; run mitmdump once to generate"
    }
}

# Output diagnostics
Log "Frida version:"
& $py.Source -c "import frida; print(frida.__version__)" 2>&1
Log "mitmproxy version:"
& $py.Source -m mitmproxy.tools.dump --version 2>&1 | Select-Object -First 3
Log "Setup complete. Next: configure POWERPNT.EXE proxy + run capture session."
Log "  Proxy: 127.0.0.1:$MitmPort"
Log "  See runbook_phase1_frida_mitm_capture.md"
