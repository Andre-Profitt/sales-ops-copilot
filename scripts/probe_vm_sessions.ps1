Write-Host "=== POWERPNT processes ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object Id, SessionId, MainWindowTitle, StartTime | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "=== qwinsta sessions ==="
qwinsta 2>&1 | Out-String | Write-Host
Write-Host "=== EXCEL processes ==="
Get-Process EXCEL -ErrorAction SilentlyContinue | Select-Object Id, SessionId | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "=== current session info ==="
Write-Host "PID = $PID"
Write-Host "SessionId of this PS = $((Get-Process -PID $PID).SessionId)"
