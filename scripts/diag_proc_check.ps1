$ErrorActionPreference = "Continue"
Get-Process | Where-Object { $_.Name -match "POWERPNT|EXCEL|WINWORD|OUTLOOK|msedge" } | Sort-Object Name | Format-Table Name, Id, MainWindowTitle, StartTime -AutoSize
Write-Output ""
Write-Output "Time on VM: $(Get-Date)"
