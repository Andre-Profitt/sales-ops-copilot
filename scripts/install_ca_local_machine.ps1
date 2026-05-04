$ProgressPreference = "SilentlyContinue"
$caPath = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
if (-not (Test-Path -LiteralPath $caPath)) { throw "CA missing: $caPath" }

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $caPath
$tp = $cert.Thumbprint
Write-Host "CA Subject: $($cert.Subject)  Thumbprint: $tp"

# certutil without -user flag targets LocalMachine
Write-Host "=== certutil -addstore -f Root (LocalMachine) ==="
$out = & certutil -addstore -f "Root" $caPath 2>&1
$out | ForEach-Object { Write-Host "  $_" }

# Verify
$rooted = Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $tp }
if ($rooted) {
    Write-Host "VERIFIED in LocalMachine\Root" -ForegroundColor Green
    exit 0
}
Write-Host "still not in LocalMachine\Root - trying X509Store .NET" -ForegroundColor Yellow

try {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine
    )
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $store.Add($cert)
    $store.Close()
    Write-Host "  X509Store LocalMachine add succeeded"
} catch {
    Write-Host "  X509Store LocalMachine add failed: $($_.Exception.Message)" -ForegroundColor Red
}

$rooted2 = Get-ChildItem -Path Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $tp }
if ($rooted2) {
    Write-Host "VERIFIED in LocalMachine\Root" -ForegroundColor Green
    exit 0
}
Write-Host "FAILED - cert not in LocalMachine\Root" -ForegroundColor Red
exit 1
