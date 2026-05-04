<#
End-to-end chain: re-pin QAT, launch PP fresh, run UIA probe for the AI button.

Assumes PP is NOT running (call Stop-Process POWERPNT before invoking).
Writes one combined log so the whole sequence is observable.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_qat_chain.log" -Force | Out-Null

# Step 1: Confirm PP not running, kill any zombies
$ppProcs = Get-Process POWERPNT -ErrorAction SilentlyContinue
if ($ppProcs) {
    Write-Output "Killing $($ppProcs.Count) lingering PP processes"
    $ppProcs | Stop-Process -Force
    Start-Sleep -Seconds 3
}

# Step 2: Re-pin QAT using the pin script (which also kills PP again as a safety)
$pinResult = & "$env:USERPROFILE\tc_qat.ps1" 2>&1
Write-Output "QAT pin run output:"
$pinResult | ForEach-Object { Write-Output "  $_" }

# Verify QAT pin got into the file
$ui = "$env:LocalAppData\Microsoft\Office\PowerPoint.officeUI"
$content = Get-Content -LiteralPath $ui -Raw
if ($content -match "tc:AISidePane") {
    Write-Output "officeUI contains tc:AISidePane: YES"
} else {
    Write-Output "officeUI contains tc:AISidePane: NO -- pin failed"
    Stop-Transcript | Out-Null
    exit 1
}

# Step 3: Launch PP cold
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Write-Output "Launching PP..."
Start-Process -FilePath $exe -ArgumentList "/N"

$deadline = (Get-Date).AddSeconds(90)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { Write-Output "PP up: pid=$($pp.Id) title='$($pp.MainWindowTitle)'"; break }
    Start-Sleep -Milliseconds 500
}

if (-not $pp) {
    Write-Output "PP did not come up within 90s"
    Stop-Transcript | Out-Null
    exit 1
}
# Give PP plenty of time for ribbon + add-ins to fully load. Earlier 5s was
# too short — probe found 0 top-band items because the ribbon hadn't populated.
Start-Sleep -Seconds 25
# Verify title is no longer "Opening - " (still loading)
$ppNow = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
Write-Output "Post-wait PP state: title='$($ppNow.MainWindowTitle)' handle=$($ppNow.MainWindowHandle)"

# Step 4: Run the QAT button UIA probe inline (so this is one log)
& "$env:USERPROFILE\tc_qat_btn.ps1" 2>&1 | ForEach-Object { Write-Output "  qat_btn: $_" }

# Step 5: Read the probe output and report
$jsonPath = "$env:USERPROFILE\tc_qat_button.json"
if (Test-Path -LiteralPath $jsonPath) {
    $j = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
    Write-Output ""
    Write-Output "=== QAT BUTTON PROBE RESULTS ==="
    Write-Output "candidate_count: $($j.candidate_count)"
    Write-Output "qat_item_count: $($j.qat_item_count)"
    if ($j.candidates.Count -gt 0) {
        Write-Output "AI CANDIDATES:"
        $j.candidates | ForEach-Object {
            Write-Output "  name=$($_.name) autoId=$($_.automationId) ctrl=$($_.controlType) bounds=$($_.bounds_xy)/$($_.bounds_wh) patterns=$($_.patterns -join ',')"
        }
    }
    if ($j.qat_items.Count -gt 0) {
        Write-Output "TOP-BAND ITEMS (first 10):"
        $j.qat_items | Select-Object -First 10 | ForEach-Object {
            Write-Output "  name=$($_.name) ctrl=$($_.controlType) bounds=$($_.bounds_xy)/$($_.bounds_wh)"
        }
    }
}

Stop-Transcript | Out-Null
