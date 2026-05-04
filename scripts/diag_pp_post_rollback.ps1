$ErrorActionPreference = "Continue"

Write-Output "=== POWERPNT processes ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding, StartTime -AutoSize

Write-Output ""
Write-Output "=== Office version registry ==="
$reg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
Write-Output "  VersionToReport: $($reg.VersionToReport)"
Write-Output "  PreviousVersionToReport: $($reg.PreviousVersionToReport)"

Write-Output ""
Write-Output "=== POWERPNT.EXE binary ==="
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
if (Test-Path $ppExe) {
    $f = Get-Item $ppExe
    Write-Output "  version: $($f.VersionInfo.FileVersion)"
    Write-Output "  modified: $($f.LastWriteTime)"
}

Write-Output ""
Write-Output "=== Last 5 crashes (last 5 min) ==="
Get-EventLog -LogName Application -After (Get-Date).AddMinutes(-5) -EntryType Error -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match "POWERPNT" } |
    Select-Object -First 5 |
    ForEach-Object {
        $msg = if ($_.Message.Length -gt 350) { $_.Message.Substring(0, 350) } else { $_.Message }
        Write-Output "[$($_.TimeGenerated) $($_.Source) #$($_.EventID)]"
        Write-Output $msg
        Write-Output ""
    }
