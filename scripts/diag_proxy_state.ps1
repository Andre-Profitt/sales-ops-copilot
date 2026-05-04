$ErrorActionPreference = "Continue"
Write-Output "=== HKCU proxy ==="
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Get-ItemProperty $reg | Select-Object ProxyEnable, ProxyServer, ProxyOverride, AutoConfigURL | Format-List

Write-Output "=== netsh winhttp ==="
& netsh winhttp show proxy

Write-Output "=== mitmdump processes ==="
Get-Process mitmdump -ErrorAction SilentlyContinue | Select-Object Id, StartTime | Format-Table -AutoSize

Write-Output "=== Test reach login.microsoft.com ==="
try {
    $r = Invoke-WebRequest "https://login.microsoftonline.com/" -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 0
    Write-Output "  status: $($r.StatusCode)"
} catch {
    Write-Output "  error: $($_.Exception.Message)"
}
