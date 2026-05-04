<#
Dump all think-cell ribbon buttons from the latest UIA discovery JSON.
#>
$j = Get-Content "$env:USERPROFILE\tc_uia_discovery.json" -Raw | ConvertFrom-Json
Write-Host "=== Buttons (count=$($j.thinkcell_ribbon_buttons.Count)) ==="
$j.thinkcell_ribbon_buttons | ForEach-Object {
    $line = "  name='" + $_.name + "' autoId='" + $_.automationId + "' bounds=" + $_.bounds
    Write-Host $line
}
