#requires -Version 5.1
<#
Phase 12 setup - resume after x64 Python install. Confirmed PE machine=x86_64.
Skip the platform.machine() sanity check (returns OS arch on Win-ARM64, misleading).
Just pip install mitmproxy + frida-tools, gen CA, trust.
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[mitm-x64] $m" -ForegroundColor $c }

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
if (-not (Test-Path -LiteralPath $pyExe)) {
    throw "x64 Python not found at $pyExe"
}

# Confirm process pointer width
$ptrBits = & $pyExe -c "import struct; print(struct.calcsize('P')*8)"
Log "Python: $((& $pyExe --version 2>&1)) (pointer bits=$ptrBits, sys.version arch token: $((& $pyExe -c \"import sys; print('AMD64' if 'AMD64' in sys.version else ('ARM64' if 'ARM64' in sys.version else '?'))\")))" Green

# 1. Upgrade pip
Log "Upgrading pip"
& $pyExe -m pip install --user --upgrade pip 2>&1 | Select-Object -Last 2 | ForEach-Object { Log "  pip: $_" }

# 2. Install mitmproxy + frida-tools (x64 wheels expected)
Log "Installing mitmproxy + frida-tools"
$pipOut = & $pyExe -m pip install --user --upgrade mitmproxy frida-tools 2>&1
$tail = $pipOut | Select-Object -Last 6
$tail | ForEach-Object { Log "  pip: $_" }

# 3. Verify mitmproxy importable
$mitmVer = & $pyExe -c "import mitmproxy; print(mitmproxy.__version__)" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "mitmproxy import failed: $mitmVer"
}
Log "mitmproxy version: $mitmVer" Green

$fridaVer = & $pyExe -c "import frida; print(frida.__version__)" 2>&1
Log "frida version: $fridaVer" Green

# 4. Find Scripts dir
$userBase = (& $pyExe -c "import site; print(site.USER_BASE)").Trim()
$candidates = @(
    "$userBase\Python313\Scripts\mitmdump.exe",
    "$userBase\Scripts\mitmdump.exe"
)
$mitmdump = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $mitmdump) {
    Log "mitmdump.exe not found; will invoke via -m mitmproxy.tools.dump" Yellow
} else {
    Log "mitmdump path: $mitmdump" Green
}

# 5. Generate CA (run mitmproxy.tools.dump briefly)
$caDir  = "$env:USERPROFILE\.mitmproxy"
$caPath = "$caDir\mitmproxy-ca-cert.cer"
if (-not (Test-Path -LiteralPath $caPath)) {
    Log "Generating CA via mitmproxy.tools.dump first-run on port 18890"
    $proc = Start-Process -FilePath $pyExe `
        -ArgumentList "-m","mitmproxy.tools.dump","-p","18890","--listen-host","127.0.0.1" `
        -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(25)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $caPath)) {
        Start-Sleep -Milliseconds 500
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if (-not (Test-Path -LiteralPath $caPath)) {
    throw "CA cert was not generated at $caPath"
}
Log "CA exists: $caPath ($((Get-Item $caPath).Length) bytes)" Green

# 6. Trust CA in CurrentUser\Root
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

# 7. Final state report
$state = [ordered]@{
    python_x64_exe       = $pyExe
    python_pointer_bits  = $ptrBits
    python_version       = ((& $pyExe --version 2>&1).ToString())
    mitmproxy_version    = $mitmVer
    frida_version        = $fridaVer
    mitmdump_path        = if ($mitmdump) { $mitmdump } else { "(invoke via -m mitmproxy.tools.dump)" }
    user_base            = $userBase
    ca_cert_path         = $caPath
    ca_cert_exists       = (Test-Path -LiteralPath $caPath)
    ca_trusted_user_root = $true
}
$state | ConvertTo-Json -Depth 4
