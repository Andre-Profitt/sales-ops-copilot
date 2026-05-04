$paths = [ordered]@{
    python_x64       = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
    mitmdump_exe     = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe"
    frida_trace_exe  = "$env:APPDATA\Python\Python313\Scripts\frida-trace.exe"
    ca_cert          = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
    capture_dir      = "$env:USERPROFILE\tc_auth"
    aiauth_bin       = "$env:APPDATA\think-cell\aiauthentication.bin"
}

Write-Host "=== Phase 12 setup state ==="
foreach ($k in $paths.Keys) {
    $exists = Test-Path -LiteralPath $paths[$k]
    $marker = if ($exists) { "OK " } else { "MISSING" }
    Write-Host ("{0,-16} {1}  {2}" -f $k, $marker, $paths[$k])
}

# CA trust state - check by thumbprint
$caPath = $paths['ca_cert']
if (Test-Path -LiteralPath $caPath) {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $caPath
    $tp = $cert.Thumbprint
    Write-Host ""
    Write-Host "CA thumbprint: $tp"
    $rooted = Get-ChildItem -Path Cert:\CurrentUser\Root -ErrorAction SilentlyContinue | Where-Object { $_.Thumbprint -eq $tp }
    if ($rooted) {
        Write-Host "CA TRUSTED in CurrentUser\Root" -ForegroundColor Green
    } else {
        Write-Host "CA NOT trusted in CurrentUser\Root - manual install needed" -ForegroundColor Yellow
    }
}
