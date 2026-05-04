<#
Recovery — clear Office's resiliency "PP crashed last time" state which is
suppressing PP startup with a Safe Mode prompt that blocks under
non-interactive Session 1.

ALSO restore PowerPoint.officeUI to the pre-QAT-pin baseline first to rule
out the QAT pin causing the crash.

Steps:
  1. Kill any POWERPNT processes
  2. Restore PowerPoint.officeUI from .bak.original
  3. Clear HKCU\Software\Microsoft\Office\16.0\PowerPoint\Resiliency\StartupItems
  4. Launch PP fresh, wait up to 90s for MainWindowTitle
  5. If PP still doesn't come up, also dismiss any open dialog via SendKeys "N"
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_recover.log" -Force | Out-Null

Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

$officeUI = "$env:LocalAppData\Microsoft\Office\PowerPoint.officeUI"
$bakOrig = "$officeUI.bak.original"
if (Test-Path -LiteralPath $bakOrig) {
    Copy-Item -LiteralPath $bakOrig -Destination $officeUI -Force
    Write-Output "Restored PowerPoint.officeUI from $bakOrig"
} else {
    Write-Output "No .bak.original to restore"
}

# Clear PP Resiliency
$resKey = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency"
foreach ($sub in @("StartupItems", "DisabledItems", "DocumentRecovery", "CrashingAddinList")) {
    $k = "$resKey\$sub"
    if (Test-Path $k) {
        Get-ChildItem -LiteralPath $k -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ItemProperty -LiteralPath $k -ErrorAction SilentlyContinue | ForEach-Object {
            $_.PSObject.Properties | Where-Object { $_.Name -notin @("PSPath","PSParentPath","PSChildName","PSDrive","PSProvider") } | ForEach-Object {
                Remove-ItemProperty -LiteralPath $k -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleared $sub"
    }
}

# Launch PP with /safe might force-skip prompt. Try regular launch first.
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Write-Output "Launching PP cold..."
Start-Process -FilePath $exe -ArgumentList "/N"

# Wait
$deadline = (Get-Date).AddSeconds(90)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"; break }
    Start-Sleep -Milliseconds 500
}

# If no main window, send 'N' to dismiss Safe Mode prompt if present
if (-not $pp) {
    Add-Type -AssemblyName System.Windows.Forms
    Write-Output "No PP main window - sending 'N' to dismiss any dialog"
    [System.Windows.Forms.SendKeys]::SendWait("n")
    Start-Sleep -Seconds 5
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 5
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "After SendKeys: PP up: pid=$($pp.Id)" } else { Write-Output "Still no PP window" }
}

if ($pp) {
    Write-Output "SUCCESS"
} else {
    Write-Output "FAILED"
    Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowHandle, MainWindowTitle, Responding -AutoSize
}
Stop-Transcript | Out-Null
