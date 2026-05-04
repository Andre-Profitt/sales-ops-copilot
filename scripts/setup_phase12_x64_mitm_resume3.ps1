#requires -Version 5.1
<#
Phase 12 setup - resume v3: simpler string interpolation (no nested subexpressions).
#>

$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[mitm-x64] $m" -ForegroundColor $c }

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
if (-not (Test-Path -LiteralPath $pyExe)) {
    Write-Host "x64 Python missing at $pyExe" -ForegroundColor Red
    exit 2
}

$ptrBits = (& $pyExe -c "import struct; print(struct.calcsize('P')*8)" 2>&1 | Out-String).Trim()
$pyVerStr = (& $pyExe --version 2>&1 | Out-String).Trim()
Log "Python: $pyVerStr (pointer bits=$ptrBits)" Green

# pip install mitmproxy + frida-tools
Log "Installing mitmproxy + frida-tools"
$pipArgs = @("-m","pip","install","--user","--upgrade","--no-warn-script-location","mitmproxy","frida-tools")
$pipOut = & $pyExe @pipArgs 2>&1 | Out-String
$exitCode = $LASTEXITCODE
$pipLines = $pipOut -split "`n"
$tail = $pipLines | Where-Object { $_.Trim() } | Select-Object -Last 8
foreach ($l in $tail) { Log "  pip: $($l.TrimEnd())" }
if ($exitCode -ne 0) {
    Log "pip exited $exitCode - full tail follows" Red
    $pipLines | Select-Object -Last 30 | ForEach-Object { Write-Host "  $_" }
    exit $exitCode
}

# Verify mitmproxy importable
$mitmVer = (& $pyExe -c "import mitmproxy; print(mitmproxy.__version__)" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    Log "mitmproxy import failed: $mitmVer" Red
    exit 1
}
Log "mitmproxy version: $mitmVer" Green

$fridaVer = (& $pyExe -c "import frida; print(frida.__version__)" 2>&1 | Out-String).Trim()
Log "frida version: $fridaVer" Green

# Generate CA
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
    Log "CA cert was not generated at $caPath" Red
    exit 1
}
$caSize = (Get-Item -LiteralPath $caPath).Length
Log "CA exists: $caPath size=$caSize" Green

# Trust CA in CurrentUser\Root
$existing = Get-ChildItem -Path Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
            Where-Object { $_.Subject -match "mitmproxy" }
if ($existing) {
    Log "CA already trusted: $($existing.Subject)" Green
} else {
    Log "Adding CA to CurrentUser\Root via certutil"
    & certutil -user -addstore -f "Root" $caPath 2>&1 | Out-Null
    $verify = Get-ChildItem -Path Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
              Where-Object { $_.Subject -match "mitmproxy" }
    if (-not $verify) {
        Log "certutil reported success but cert not found in CurrentUser\Root" Red
        exit 1
    }
    Log "CA trusted: $($verify.Subject)" Green
}

# Locate mitmdump.exe
$userBase = (& $pyExe -c "import site; print(site.USER_BASE)" 2>&1 | Out-String).Trim()
$candidates = @(
    "$userBase\Python313\Scripts\mitmdump.exe",
    "$userBase\Scripts\mitmdump.exe"
)
$mitmdump = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($mitmdump) { Log "mitmdump path: $mitmdump" Green }

$state = [ordered]@{
    python_x64_exe       = $pyExe
    python_pointer_bits  = [int]$ptrBits
    mitmproxy_version    = $mitmVer
    frida_version        = $fridaVer
    mitmdump_path        = if ($mitmdump) { $mitmdump } else { "(invoke via -m mitmproxy.tools.dump)" }
    user_base            = $userBase
    ca_cert_path         = $caPath
    ca_cert_size         = $caSize
    ca_trusted_user_root = $true
}
Write-Host "PHASE12_STATE_BEGIN"
$state | ConvertTo-Json -Depth 4
Write-Host "PHASE12_STATE_END"
