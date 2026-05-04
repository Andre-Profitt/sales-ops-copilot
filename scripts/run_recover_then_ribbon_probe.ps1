<#
Single-shot: recover PP, then IMMEDIATELY run deep ribbon MSAA probe.
The 25-30 second window between PP "Opening - " → "Presentation1 - PowerPoint"
→ zombie is the only opportunity. Combine recovery + probe in one transcript.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_recover_probe.log" -Force | Out-Null

# Kill any PP
Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

# Clear Resiliency
$resKey = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency"
foreach ($sub in @("StartupItems","DisabledItems","DocumentRecovery","CrashingAddinList")) {
    $k = "$resKey\$sub"
    if (Test-Path $k) {
        Get-ItemProperty -LiteralPath $k -ErrorAction SilentlyContinue | ForEach-Object {
            $_.PSObject.Properties | Where-Object { $_.Name -notin @("PSPath","PSParentPath","PSChildName","PSDrive","PSProvider") } | ForEach-Object {
                Remove-ItemProperty -LiteralPath $k -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
Write-Output "Resiliency cleared"

# Launch PP cold
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $exe -ArgumentList "/N"
Write-Output "PP launched"

# Wait for MainWindowTitle (quick poll)
$deadline = (Get-Date).AddSeconds(60)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $pp) {
    Write-Output "PP did not come up in 60s"
    Stop-Transcript | Out-Null
    exit 1
}
Write-Output "PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"

# Wait for ribbon to populate (10s — shorter than 25s to beat the zombie clock)
Start-Sleep -Seconds 10

# Verify still healthy
$ppNow = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
if (-not $ppNow -or -not $ppNow.MainWindowHandle) {
    Write-Output "PP zombied during 10s wait - title='$($ppNow.MainWindowTitle)' handle=$($ppNow.MainWindowHandle)"
    Stop-Transcript | Out-Null
    exit 2
}
Write-Output "Post-wait healthy: title='$($ppNow.MainWindowTitle)' handle=$($ppNow.MainWindowHandle)"

# Run the deep ribbon probe inline
& "$env:USERPROFILE\tc_ribbon.ps1" 2>&1 | ForEach-Object { Write-Output "  ribbon: $_" }

# Report results
$jsonPath = "$env:USERPROFILE\tc_ribbon_deep.json"
if (Test-Path -LiteralPath $jsonPath) {
    $j = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
    Write-Output ""
    Write-Output "=== RIBBON DEEP PROBE RESULTS ==="
    Write-Output "ribbon_hwnd: $($j.ribbon_hwnd)"
    Write-Output "tab_selected: $($j.tab_selected)"
    Write-Output "accessible_count: $($j.accessible_count)"
    Write-Output "candidate_count: $($j.candidate_count)"
    Write-Output "errors: $($j.errors.Count)"
    $j.errors | Select-Object -First 5 | ForEach-Object { Write-Output "  err: $_" }

    if ($j.candidates.Count -gt 0) {
        Write-Output "AI CANDIDATES:"
        $j.candidates | ForEach-Object {
            Write-Output "  name='$($_.name)' role=$($_.role) defAction='$($_.defAction)' loc=$($_.loc) crumb=$($_.breadcrumb)"
        }
    }

    Write-Output "FIRST 30 NAMED ACCESSIBLES:"
    $j.accessibles | Where-Object { $_.name } | Select-Object -First 30 | ForEach-Object {
        Write-Output "  d=$($_.depth) role=$($_.role) name='$($_.name)' loc=$($_.loc) crumb='$($_.breadcrumb)'"
    }
}

Write-Output "DONE"
Stop-Transcript | Out-Null
