$ErrorActionPreference = "Continue"
Write-Output "=== ALL processes matching 'powerp' (case-insensitive) ==="
Get-Process | Where-Object { $_.Name -match "(?i)powerp" } | Format-Table Id, Name, MainWindowHandle, MainWindowTitle, SessionId, StartTime -AutoSize
Write-Output ""
Write-Output "=== POWERPNT via WMI (more reliable) ==="
Get-CimInstance -ClassName Win32_Process -Filter "Name like '%POWERPNT%'" -ErrorAction SilentlyContinue |
    Select-Object ProcessId, Name, SessionId, CommandLine, CreationDate | Format-List
Write-Output ""
Write-Output "=== Sessions ==="
& query session
