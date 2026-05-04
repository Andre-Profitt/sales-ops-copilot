$ProgressPreference = "SilentlyContinue"
$caPath = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
if (-not (Test-Path -LiteralPath $caPath)) { throw "CA missing: $caPath" }

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $caPath
Write-Host "Subject: $($cert.Subject)  Thumbprint: $($cert.Thumbprint)"

# Method 1: Import-Certificate cmdlet
Write-Host "=== Attempt 1: Import-Certificate ==="
try {
    Import-Certificate -FilePath $caPath -CertStoreLocation Cert:\CurrentUser\Root -ErrorAction Stop | Out-Null
    Write-Host "  Import-Certificate succeeded"
} catch {
    Write-Host "  Import-Certificate failed: $($_.Exception.Message)"
}

$check1 = Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
if ($check1) {
    Write-Host "  VERIFIED in CurrentUser\Root after Import-Certificate"
    exit 0
}

# Method 2: Direct .NET X509Store
Write-Host "=== Attempt 2: System.Security.Cryptography.X509Certificates.X509Store ==="
try {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
        [System.Security.Cryptography.X509Certificates.StoreName]::Root,
        [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
    )
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $store.Add($cert)
    $store.Close()
    Write-Host "  X509Store add succeeded"
} catch {
    Write-Host "  X509Store add failed: $($_.Exception.Message)"
}

$check2 = Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
if ($check2) {
    Write-Host "  VERIFIED in CurrentUser\Root after X509Store"
    exit 0
}

# Method 3: certutil with no -user flag (machine store, requires admin) - skip; user store is target

# Method 4: certmgr.msc (interactive) - cannot do over SSH

Write-Host "=== ALL HEADLESS METHODS FAILED ==="
Write-Host "Cert is NOT trusted in any store. mitmproxy interception will fail TLS verification."
Write-Host ""
Write-Host "Manual fallback for Andre (1 click):"
Write-Host "  Double-click $caPath in File Explorer"
Write-Host "  Click 'Install Certificate'"
Write-Host "  Choose 'Current User'"
Write-Host "  Choose 'Place all certificates in the following store'"
Write-Host "  Browse - select 'Trusted Root Certification Authorities'"
Write-Host "  Click OK on the security warning."
exit 1
