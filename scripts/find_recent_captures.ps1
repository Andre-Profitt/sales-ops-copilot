$ErrorActionPreference = "Continue"
Write-Output "=== Time on VM ==="
Get-Date
Write-Output ""
Write-Output "=== Latest 5 capture dirs ==="
Get-ChildItem C:\Users\test\tc_aicore_captures -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Desc | Select-Object -First 5 | Format-Table FullName, LastWriteTime -AutoSize

Write-Output "=== Files modified in last 30 min in capture dirs ==="
Get-ChildItem C:\Users\test\tc_aicore_captures -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-30) } |
    Sort-Object LastWriteTime -Desc |
    Select-Object -First 10 |
    Format-Table FullName, Length, LastWriteTime -AutoSize

Write-Output "=== Recent mitm flow files anywhere ==="
Get-ChildItem C:\Users\test -Recurse -Include "mitm.flow", "mitm.har" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-30) } |
    Sort-Object LastWriteTime -Desc |
    Format-Table FullName, Length, LastWriteTime -AutoSize

Write-Output "=== Any mitmdump processes still running? ==="
Get-Process mitmdump -ErrorAction SilentlyContinue | Format-Table Id, StartTime -AutoSize

Write-Output "=== POWERPNT state ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, StartTime -AutoSize
