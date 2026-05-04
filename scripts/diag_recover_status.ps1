<# Check recovery schtask + log + PP state. #>
$ErrorActionPreference = "Continue"
Write-Output "=== schtasks (tc_recover*) ==="
schtasks /query /fo list 2>&1 | Out-String -Width 200 | ForEach-Object { $_.Split("`n") } | Where-Object { $_ -match "tc_recover|TaskName:" } | Select-Object -First 30 | ForEach-Object { Write-Output $_ }

Write-Output ""
Write-Output "=== tc_recover.log ==="
if (Test-Path "$env:USERPROFILE\tc_recover.log") {
    Get-Content "$env:USERPROFILE\tc_recover.log" -Raw
} else {
    Write-Output "NOT_FOUND"
}

Write-Output ""
Write-Output "=== POWERPNT ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
