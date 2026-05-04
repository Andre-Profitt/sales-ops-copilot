<#
Phase 12 capture environment setup - runnable via SSH non-interactive.

Bypasses the Microsoft Store stubs by downloading Python 3.13 directly from
python.org and installing per-user (no admin needed). Then installs Frida +
mitmproxy via pip, generates the mitmproxy CA, and trusts it in the
CurrentUser root store (no admin needed via the -user flag).

Idempotent. Safe to re-run. Reports state at every step.
#>
[CmdletBinding()]
param(
    [string] $PythonVersion = "3.13.1",
    [switch] $Force
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Log {
    param($msg, [ConsoleColor] $color = "Gray")
    Write-Host "[setup] $msg" -ForegroundColor $color
}

# ---------- 1. Python ----------
$pythonExe = $null
foreach ($candidate in @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313-arm64\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
)) {
    if (Test-Path -LiteralPath $candidate) { $pythonExe = $candidate; break }
}
if (-not $pythonExe -and -not $Force) {
    # Try existing python on PATH (excluding the WindowsApps stub)
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch "WindowsApps") {
        $pythonExe = $cmd.Source
    }
}

if (-not $pythonExe -or $Force) {
    Log "Python not installed (or --Force). Downloading python.org installer..." Yellow
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-$arch.exe"
    $installer = "$env:TEMP\python-$PythonVersion-$arch.exe"
    Log "URL: $url"
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    Log "Downloaded $((Get-Item $installer).Length) bytes"
    Log "Running silent install (per-user, no admin required)..."
    # /quiet runs without UI, PrependPath adds to PATH, InstallAllUsers=0 is per-user
    $proc = Start-Process -FilePath $installer -ArgumentList @(
        "/quiet",
        "PrependPath=1",
        "InstallAllUsers=0",
        "Include_test=0",
        "Include_doc=0",
        "Include_launcher=0"
    ) -Wait -PassThru
    Log "Installer exit code: $($proc.ExitCode)"
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    # Check again
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313-arm64\python.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) { $pythonExe = $candidate; break }
    }
}

if (-not $pythonExe) {
    Log "ERROR: Python install failed. Check %LOCALAPPDATA%\Programs\Python\" Red
    exit 1
}
$pythonDir = Split-Path -Parent $pythonExe
$scriptsDir = Join-Path $pythonDir "Scripts"
$env:PATH = "$pythonDir;$scriptsDir;$env:PATH"
Log "Python: $pythonExe" Green
Log "Version: $(& $pythonExe --version 2>&1)"

# ---------- 2. pip install frida-tools + mitmproxy ----------
Log "Upgrading pip..."
& $pythonExe -m pip install --upgrade pip 2>&1 | Where-Object { $_ -match '^Successfully|already' } | Select-Object -Last 3

Log "Installing frida-tools (this takes a minute)..."
& $pythonExe -m pip install --upgrade frida-tools 2>&1 | Where-Object { $_ -match '^Successfully|already' } | Select-Object -Last 3

Log "Installing mitmproxy (this takes a minute)..."
& $pythonExe -m pip install --upgrade mitmproxy 2>&1 | Where-Object { $_ -match '^Successfully|already' } | Select-Object -Last 3

# Verify
$fridaVer = & $pythonExe -c "import frida; print(frida.__version__)" 2>&1
$mitmVer = & $pythonExe -c "import mitmproxy; print(mitmproxy.__version__)" 2>&1
Log "Frida: $fridaVer"
Log "mitmproxy: $mitmVer"

# ---------- 3. Generate mitmproxy CA cert ----------
$caPath = Join-Path $env:USERPROFILE ".mitmproxy\mitmproxy-ca-cert.cer"
if (-not (Test-Path -LiteralPath $caPath) -or $Force) {
    Log "Generating mitmproxy CA cert (running mitmdump for 4s)..."
    $proc = Start-Process -FilePath $pythonExe -ArgumentList @("-m", "mitmproxy.tools.dump", "-p", "8889", "-q") -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 4
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if (Test-Path -LiteralPath $caPath) {
    Log "CA cert: $caPath ($((Get-Item $caPath).Length) bytes)" Green
} else {
    Log "ERROR: mitmproxy CA cert not generated. Try: $pythonExe -m mitmproxy.tools.dump" Red
}

# ---------- 4. Trust CA in CurrentUser root store (no admin needed) ----------
$existingTrust = Get-ChildItem -Path Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -match "mitmproxy" }
if ($existingTrust -and -not $Force) {
    Log "CA already trusted in CurrentUser\Root: $($existingTrust.Subject)" Green
} elseif (Test-Path -LiteralPath $caPath) {
    Log "Trusting CA in CurrentUser\Root (no admin needed)..."
    $result = certutil -user -addstore -f "Root" $caPath 2>&1
    Log ($result | Out-String).Trim()
    $verify = Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object { $_.Subject -match "mitmproxy" }
    if ($verify) {
        Log "CA trusted: $($verify.Subject)" Green
    } else {
        Log "WARN: certutil reported success but cert not found in CurrentUser\Root" Yellow
    }
}

# ---------- 5. Verify aiauthentication.bin exists (so capture has something to refresh) ----------
$aiauthPath = "$env:APPDATA\think-cell\aiauthentication.bin"
if (Test-Path -LiteralPath $aiauthPath) {
    Log "aiauthentication.bin: present, $((Get-Item $aiauthPath).Length) bytes" Green
} else {
    Log "WARN: aiauthentication.bin missing - open PowerPoint with think-cell once before capture to populate it" Yellow
}

# ---------- 6. Capture working directory ----------
$cap = "$env:USERPROFILE\tc_auth"
New-Item -ItemType Directory -Path $cap -Force | Out-Null
Log "Capture dir ready: $cap"

# ---------- 7. Final state report ----------
Log "" Cyan
Log "=========================================" Cyan
Log "READY FOR PHASE 12 CAPTURE" Cyan
Log "=========================================" Cyan
$state = [ordered]@{
    python_exe = $pythonExe
    python_version = (& $pythonExe --version 2>&1)
    frida_version = $fridaVer
    mitmproxy_version = $mitmVer
    ca_cert_path = $caPath
    ca_cert_exists = (Test-Path -LiteralPath $caPath)
    ca_trusted_user_root = ($null -ne (Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object { $_.Subject -match "mitmproxy" }))
    aiauth_bin_present = (Test-Path -LiteralPath $aiauthPath)
    aiauth_bin_size = if (Test-Path -LiteralPath $aiauthPath) { (Get-Item $aiauthPath).Length } else { 0 }
    capture_dir = $cap
    powerpoint_running = ((Get-Process POWERPNT -ErrorAction SilentlyContinue) -ne $null)
}
$state | ConvertTo-Json
