#requires -Version 5.1
<#
Phase 12 finalize: install confirmed; just gen CA + trust + emit state.
#>

$ProgressPreference = "SilentlyContinue"
function Log($m, $c="Cyan") { Write-Host "[finalize] $m" -ForegroundColor $c }

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"

# Correct version probes
$mitmVer  = (& $pyExe -c "from mitmproxy import version; print(version.VERSION)" 2>&1 | Out-String).Trim()
$fridaVer = (& $pyExe -c "import frida; print(frida.__version__)" 2>&1 | Out-String).Trim()
Log "mitmproxy: $mitmVer  frida: $fridaVer" Green

# Generate CA
$caDir  = "$env:USERPROFILE\.mitmproxy"
$caPath = "$caDir\mitmproxy-ca-cert.cer"
if (-not (Test-Path -LiteralPath $caPath)) {
    Log "Generating CA via mitmdump first-run on port 18890"
    $proc = Start-Process -FilePath $pyExe `
        -ArgumentList "-m","mitmproxy.tools.dump","-p","18890","--listen-host","127.0.0.1" `
        -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $caPath)) {
        Start-Sleep -Milliseconds 500
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if (-not (Test-Path -LiteralPath $caPath)) {
    Log "CA cert was not generated at $caPath" Red
    Log "Listing $caDir contents:" Yellow
    if (Test-Path -LiteralPath $caDir) {
        Get-ChildItem -LiteralPath $caDir -Force | Format-Table Name,Length,LastWriteTime -AutoSize | Out-String | Write-Host
    } else {
        Log "  $caDir does not exist" Yellow
    }
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

# Final state report
$state = [ordered]@{
    python_x64_exe       = $pyExe
    mitmproxy_version    = $mitmVer
    frida_version        = $fridaVer
    mitmdump_path        = if ($mitmdump) { $mitmdump } else { "(invoke via -m mitmproxy.tools.dump)" }
    user_base            = $userBase
    ca_cert_path         = $caPath
    ca_cert_size         = $caSize
    ca_trusted_user_root = $true
    aiauth_bin_present   = (Test-Path -LiteralPath "$env:APPDATA\think-cell\aiauthentication.bin")
    capture_dir          = "$env:USERPROFILE\tc_auth"
    capture_dir_exists   = (Test-Path -LiteralPath "$env:USERPROFILE\tc_auth")
}
Write-Host "PHASE12_STATE_BEGIN"
$state | ConvertTo-Json -Depth 4
Write-Host "PHASE12_STATE_END"
