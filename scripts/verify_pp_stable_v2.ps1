<# Verify PP stable on 19822 with longer cold-start tolerance. #>
$ErrorActionPreference = "Continue"

Stop-Process -Name POWERPNT -Force -ErrorAction SilentlyContinue
Start-Sleep 2

Write-Output "Launching POWERPNT (cold start, may take 60-90s)..."
Start-Process "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE" -ArgumentList "/N"

# Wait up to 120s for window
$d = (Get-Date).AddSeconds(120)
$pp = $null
$lastReport = Get-Date
while ((Get-Date) -lt $d) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "[+] PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)' after $([int]((Get-Date) - ((Get-Date).AddSeconds(-120))).TotalSeconds)s"; break }
    if (((Get-Date) - $lastReport).TotalSeconds -gt 10) {
        $allPP = Get-Process POWERPNT -ErrorAction SilentlyContinue
        Write-Output "  poll: $($allPP.Count) PP procs"
        $allPP | ForEach-Object {
            Write-Output "    pid=$($_.Id) hwnd=$($_.MainWindowHandle) title='$($_.MainWindowTitle)' resp=$($_.Responding)"
        }
        $lastReport = Get-Date
    }
    Start-Sleep -Milliseconds 500
}

if (-not $pp) {
    Write-Output "PP didn't get window in 120s. Final state:"
    Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
    exit 1
}

# Verify still alive after 30s
Start-Sleep 30
$pp2 = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if ($pp2) {
    Write-Output "[T+30] STILL ALIVE: pid=$($pp2.Id) title='$($pp2.MainWindowTitle)'"
    Write-Output "REGRESSION FIXED -- PP is stable on 19822"
} else {
    Write-Output "[T+30] PP zombied"
    Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
    Write-Output "STILL BROKEN"
}
