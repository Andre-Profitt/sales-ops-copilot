$ErrorActionPreference = "Continue"
$killed = Get-Process POWERPNT, WINWORD, EXCEL, OUTLOOK, ONENOTE, msedgewebview2 -ErrorAction SilentlyContinue
$count = $killed.Count
$killed | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 3
Write-Output "Killed $count zombie processes."
Write-Output ""
Write-Output "Remaining (should be 0):"
Get-Process POWERPNT, msedgewebview2 -ErrorAction SilentlyContinue | Format-Table Name, Id, MainWindowTitle -AutoSize
Write-Output "READY -- open PowerPoint manually via Start menu now."
