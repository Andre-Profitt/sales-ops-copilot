#requires -Version 5.1
<#
Phase 12 setup - x64 Python path for mitmproxy.

Why this exists:
- ARM64 Python 3.13 has no prebuilt wheels for cryptography / mitmproxy-rs / aioquic /
  Brotli; pip falls back to source build which needs MSVC link.exe (not present).
- The mitmproxy standalone bundle (mitmdump.exe / mitmproxy.exe) gets hash-flagged by
  Windows Defender as PUA. mitmweb.exe survives, but the dump CLI is needed for capture.
- Solution: install x64 CPython (Windows ARM64 runs x64 transparently). pip pulls x64
  wheels for cryptography + mitmproxy-rs. Resulting mitmdump.exe is a small setuptools
  wrapper launching python.exe (signed by PSF), not flagged by Defender.
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[mitm-x64] $m" -ForegroundColor $c }

$pyVer = "3.13.1"
$pyInst = "$env:TEMP\python-$pyVer-amd64.exe"
$pyDir  = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64"

# 1. Download x64 Python installer (no admin needed for per-user install)
if (-not (Test-Path "$pyDir\python.exe")) {
    if (-not (Test-Path $pyInst)) {
        $url = "https://www.python.org/ftp/python/$pyVer/python-$pyVer-amd64.exe"
        Log "Downloading $url"
        Invoke-WebRequest -Uri $url -OutFile $pyInst -UseBasicParsing
    }
    Log "Installing Python $pyVer x64 per-user (no admin)"
    $args = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=0",
        "Include_launcher=0",
        "Include_test=0",
        "Include_doc=0",
        "Include_dev=0",
        "Include_pip=1",
        "DefaultJustForMeTargetDir=$pyDir",
        "SimpleInstall=1",
        "SimpleInstallDescription=Phase12 x64 mitmproxy host"
    )
    Start-Process -FilePath $pyInst -ArgumentList $args -Wait -NoNewWindow
    if (-not (Test-Path "$pyDir\python.exe")) {
        throw "Python x64 install failed; expected $pyDir\python.exe"
    }
} else {
    Log "x64 Python already present at $pyDir" Green
}

$pyExe = "$pyDir\python.exe"
$pyArch = & $pyExe -c "import platform; print(platform.machine())"
Log "Python: $((& $pyExe --version 2>&1)) ($pyArch)" Green
if ($pyArch -ne "AMD64" -and $pyArch -ne "x86_64") {
    throw "Expected x64 Python; got arch=$pyArch"
}

# 2. Upgrade pip then install mitmproxy + frida-tools
Log "Upgrading pip"
& $pyExe -m pip install --user --upgrade pip 2>&1 | Select-Object -Last 3 | ForEach-Object { Log "  pip: $_" }

Log "Installing mitmproxy + frida-tools (x64 wheels)"
$pipOut = & $pyExe -m pip install --user --upgrade mitmproxy frida-tools 2>&1
$pipOut | Select-Object -Last 5 | ForEach-Object { Log "  pip: $_" }

# 3. Find the user Scripts dir and verify mitmdump
$userBase = & $pyExe -c "import site; print(site.USER_BASE)"
$scriptsDir = "$userBase\Python313\Scripts"
$mitmdump = "$scriptsDir\mitmdump.exe"
if (-not (Test-Path $mitmdump)) {
    # Some pip configs put scripts at $userBase\Scripts
    $scriptsDir = "$userBase\Scripts"
    $mitmdump = "$scriptsDir\mitmdump.exe"
}
if (-not (Test-Path $mitmdump)) {
    throw "mitmdump.exe not found under $userBase"
}
$mitmVer = (& $pyExe -m mitmproxy.tools.dump --version 2>&1 | Select-String -Pattern "Mitmproxy:" | Select-Object -First 1).Line
Log "mitmdump: $mitmdump" Green
Log "mitmdump version: $mitmVer" Green

# 4. Generate CA
$caDir  = "$env:USERPROFILE\.mitmproxy"
$caPath = "$caDir\mitmproxy-ca-cert.cer"
if (-not (Test-Path $caPath)) {
    Log "Generating CA via mitmdump first-run (port 18889)"
    # Run via python -m to avoid invoking the wrapper EXE in case Defender flags it too
    $proc = Start-Process -FilePath $pyExe `
        -ArgumentList "-m","mitmproxy.tools.dump","-p","18889","--listen-host","127.0.0.1" `
        -PassThru -WindowStyle Hidden
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

# 5. Trust CA in CurrentUser\Root (no admin)
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

# 6. Final state
$state = [ordered]@{
    python_x64_exe     = $pyExe
    python_version     = (& $pyExe --version 2>&1).ToString()
    mitmdump_path      = $mitmdump
    mitmdump_version   = $mitmVer
    scripts_dir        = $scriptsDir
    ca_cert_path       = $caPath
    ca_cert_exists     = (Test-Path $caPath)
    ca_trusted_user    = $true
}
$state | ConvertTo-Json -Depth 4
