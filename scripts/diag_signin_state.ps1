$ErrorActionPreference = "Continue"

Write-Output "=== All Office processes ==="
Get-Process WINWORD, EXCEL, POWERPNT, OUTLOOK, ONENOTE, OfficeClickToRun, msedgewebview2 -ErrorAction SilentlyContinue | Format-Table Name, Id, MainWindowHandle, MainWindowTitle, StartTime -AutoSize

Write-Output ""
Write-Output "=== Identity registry ==="
$id = "HKCU:\Software\Microsoft\Office\16.0\Common\Identity\Identities"
if (Test-Path $id) {
    Get-ChildItem $id -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        Write-Output "  $($_.PSChildName)"
        Write-Output "    EmailAddress: $($p.EmailAddress)"
        Write-Output "    FriendlyName: $($p.FriendlyName)"
        Write-Output "    DisplayName: $($p.DisplayName)"
    }
} else {
    Write-Output "  no Identities registered"
}

Write-Output ""
Write-Output "=== Active sessions ==="
& query session 2>&1
