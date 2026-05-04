<# Diagnose why PP won't fully start (no MainWindowTitle). #>
$ErrorActionPreference = "Continue"

Write-Output "=== sessions ==="
& query session 2>&1

Write-Output ""
Write-Output "=== POWERPNT processes ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize

Write-Output ""
Write-Output "=== Recent Application errors (last 10) ==="
Get-EventLog -LogName Application -Newest 10 -EntryType Error -ErrorAction SilentlyContinue |
    Select-Object TimeGenerated, Source, EventID |
    Format-Table -AutoSize

Write-Output ""
Write-Output "=== Recent Office-y events ==="
Get-EventLog -LogName Application -Newest 30 -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -match "(?i)office|powerp|MSO|Setup" -or $_.Message -match "(?i)POWERPNT" } |
    Select-Object -First 5 TimeGenerated, Source, EventID, Message |
    Format-Table -AutoSize -Wrap

Write-Output ""
Write-Output "=== PowerPoint.officeUI state ==="
$ui = "$env:LocalAppData\Microsoft\Office\PowerPoint.officeUI"
if (Test-Path -LiteralPath $ui) {
    $sz = (Get-Item -LiteralPath $ui).Length
    Write-Output "size=$sz"
    Get-Content -LiteralPath $ui -Raw | Out-String | Select-Object -First 1 | ForEach-Object { Write-Output ($_.Substring(0, [Math]::Min(800, $_.Length))) }
}
