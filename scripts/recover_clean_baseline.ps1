<#
Wipe ALL Office UI customization caches so the QAT pin starts from a truly
clean baseline. Steps:
  1. Kill PP
  2. Delete officeUI + every .bak.* (forces Office to regenerate defaults)
  3. Clear Resiliency
  4. Launch PP cold so Office writes a fresh empty officeUI
  5. Confirm pp_up + write success
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_clean.log" -Force | Out-Null

Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

$officeDir = "$env:LocalAppData\Microsoft\Office"
$ui = "$officeDir\PowerPoint.officeUI"
$bakOrig = "$ui.bak.original"

Get-ChildItem -Path $officeDir -Filter "PowerPoint.officeUI*" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
    Write-Output "Deleted $($_.Name)"
}

# Clear Resiliency
$resKey = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency"
foreach ($sub in @("StartupItems", "DisabledItems", "DocumentRecovery", "CrashingAddinList")) {
    $k = "$resKey\$sub"
    if (Test-Path $k) {
        Get-ItemProperty -LiteralPath $k -ErrorAction SilentlyContinue | ForEach-Object {
            $_.PSObject.Properties | Where-Object { $_.Name -notin @("PSPath","PSParentPath","PSChildName","PSDrive","PSProvider") } | ForEach-Object {
                Remove-ItemProperty -LiteralPath $k -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Output "Cleared $sub"
    }
}

# Launch PP cold to let Office regenerate officeUI defaults
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $exe -ArgumentList "/N"

$deadline = (Get-Date).AddSeconds(90)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"; break }
    Start-Sleep -Milliseconds 500
}
if (-not $pp) {
    Write-Output "PP did not start"
    Stop-Transcript | Out-Null
    exit 1
}

# Wait for ribbon to fully load + officeUI to be written by Office
Start-Sleep -Seconds 25
Write-Output "Post-wait title='$((Get-Process -Id $pp.Id).MainWindowTitle)'"

if (Test-Path -LiteralPath $ui) {
    $sz = (Get-Item -LiteralPath $ui).Length
    Write-Output "officeUI regenerated: size=$sz"
} else {
    Write-Output "officeUI NOT written by Office (still missing)"
}

Write-Output "SUCCESS"
Stop-Transcript | Out-Null
