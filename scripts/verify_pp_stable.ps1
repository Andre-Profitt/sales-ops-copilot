<# Confirm PP launches and stays stable on 19822 (regression should be gone). #>
$ErrorActionPreference = "Continue"

# Clear Resiliency from past crashes
foreach ($sub in @("StartupItems","DisabledItems","DocumentRecovery","CrashingAddinList")) {
    $k = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency\$sub"
    if (Test-Path $k) {
        Get-ItemProperty $k -ErrorAction SilentlyContinue | ForEach-Object {
            $_.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
                Remove-ItemProperty $k -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
Stop-Process -Name POWERPNT -Force -ErrorAction SilentlyContinue
Start-Sleep 2

Start-Process "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE" -ArgumentList "/N"

$d = (Get-Date).AddSeconds(45)
$pp = $null
while ((Get-Date) -lt $d) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "[+T0] PP up: pid=$($pp.Id) title=$($pp.MainWindowTitle)"; break }
    Start-Sleep -Milliseconds 500
}

if (-not $pp) { Write-Output "[!] PP never came up in 45s"; exit 1 }

Start-Sleep 30
$pp2 = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if ($pp2) {
    Write-Output "[+T30] STILL ALIVE: pid=$($pp2.Id) hwnd=$($pp2.MainWindowHandle) title=$($pp2.MainWindowTitle)"
    Write-Output "REGRESSION FIXED"
} else {
    Write-Output "[+T30] PP zombied/died"
    Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
    Write-Output "STILL BROKEN"
}
