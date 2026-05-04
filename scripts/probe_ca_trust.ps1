$ca = "$env:USERPROFILE\.mitmproxy\mitmproxy-ca-cert.cer"
$certObj = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ca
Write-Host "FILE Subject: $($certObj.Subject)"
Write-Host "FILE Issuer:  $($certObj.Issuer)"
Write-Host "FILE Thumbprint: $($certObj.Thumbprint)"
Write-Host ""
Write-Host "--- CurrentUser\Root certs (subject contains mitm/proxy/test.user) ---"
$tp = $certObj.Thumbprint
Get-ChildItem -Path Cert:\CurrentUser\Root |
    Where-Object { $_.Subject -match "(?i)mitm|proxy" -or $_.Thumbprint -eq $tp } |
    Select-Object Subject, Thumbprint |
    Format-Table -AutoSize | Out-String | Write-Host

Write-Host "--- Match by exact thumbprint $tp ---"
$match = Get-ChildItem -Path Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $tp }
if ($match) {
    Write-Host "PRESENT: $($match.Subject)"
} else {
    Write-Host "ABSENT - thumbprint $tp not in CurrentUser\Root"
}
