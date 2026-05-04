#requires -Version 5.1
<#
Phase 12 finalize v2: use the pip-installed mitmdump.exe wrapper directly.
#>
$ProgressPreference = "SilentlyContinue"
function Log($m, $c="Cyan") { Write-Host "[finalize] $m" -ForegroundColor $c }

$pyExe       = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
$mitmdumpExe = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe"

if (-not (Test-Path -LiteralPath $mitmdumpExe)) {
    Log "mitmdump.exe not found at $mitmdumpExe" Red
    exit 2
}

# Versions
$mitmVer  = (& $pyExe -c "from mitmproxy import version; print(version.VERSION)" 2>&1 | Out-String).Trim()
$fridaVer = (& $pyExe -c "import frida; print(frida.__version__)" 2>&1 | Out-String).Trim()
Log "mitmproxy: $mitmVer  frida: $fridaVer  mitmdump.exe: $mitmdumpExe" Green

# Generate CA via the actual EXE wrapper
$caDir  = "$env:USERPROFILE\.mitmproxy"
$caPath = "$caDir\mitmproxy-ca-cert.cer"
if (-not (Test-Path -LiteralPath $caPath)) {
    Log "Generating CA via mitmdump.exe first-run on port 18890"
    $proc = Start-Process -FilePath $mitmdumpExe `
        -ArgumentList "-p","18890","--listen-host","127.0.0.1" `
        -PassThru -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $caPath)) {
        Start-Sleep -Milliseconds 500
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
if (-not (Test-Path -LiteralPath $caPath)) {
    Log "CA cert was not generated at $caPath" Red
    if (Test-Path -LiteralPath $caDir) {
        Get-ChildItem -LiteralPath $caDir -Force | Format-Table Name,Length -AutoSize | Out-String | Write-Host
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

# Final state
$state = [ordered]@{
    python_x64_exe       = $pyExe
    mitmdump_exe         = $mitmdumpExe
    mitmproxy_version    = $mitmVer
    frida_version        = $fridaVer
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
