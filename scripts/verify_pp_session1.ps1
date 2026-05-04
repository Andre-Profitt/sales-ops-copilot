<# Launch PP via schtasks in Session 1 + verify stable. #>
$ErrorActionPreference = "Continue"

Stop-Process -Name POWERPNT -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# Write a tiny launcher script + schedule THAT (avoids quoting hell)
$launcher = "$env:USERPROFILE\tc_pp_launcher.ps1"
@'
Start-Process "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE" -ArgumentList "/N"
Start-Sleep -Seconds 90
'@ | Set-Content -LiteralPath $launcher -Force

$tn = "tc_pp_verify_$(Get-Date -Format yyyyMMddHHmmss)"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$launcher`""

Write-Output "Scheduling PP launch via schtasks in Session 1..."
$st = (Get-Date).AddMinutes(1).ToString("HH:mm")
& schtasks.exe /create /sc once /st $st /tn $tn /tr $cmd /it /rl limited /f 2>&1 | Select-Object -Last 1
& schtasks.exe /run /tn $tn 2>&1 | Select-Object -Last 1

# Wait for window
$d = (Get-Date).AddSeconds(120)
$pp = $null
while ((Get-Date) -lt $d) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "[+] PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"; break }
    Start-Sleep -Seconds 2
}

if (-not $pp) {
    Write-Output "[!] PP didn't get window in 120s"
    Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
    exit 1
}

Start-Sleep 30
$pp2 = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if ($pp2) {
    Write-Output "[T+30] STILL ALIVE: pid=$($pp2.Id) title='$($pp2.MainWindowTitle)'"
    Write-Output "REGRESSION FIXED -- PP is stable"
} else {
    Write-Output "[T+30] PP zombied"
    Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
    Write-Output "STILL BROKEN"
}
