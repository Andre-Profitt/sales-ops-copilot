<#
Filter the dumped UIA invokables for AI-relevant + ribbon-area entries.
#>
$j = Get-Content "$env:USERPROFILE\tc_invokables.json" -Raw | ConvertFrom-Json
Write-Host "=== Total invokables: $($j.invokable_count) ==="
Write-Host ""

Write-Host "=== Names matching AI/insight/smart/copilot/pane/elements/gallery ==="
$j.invokables | Where-Object {
    $_.name -match "AI|insight|smart|copilot|pane|elements|gallery|tool|chat|prompt|generate"
} | ForEach-Object {
    "  '" + $_.name + "' [" + $_.controlType + "] xy=" + $_.bounds_xy + " wh=" + $_.bounds_wh + " autoId='" + $_.automationId + "'"
} | ForEach-Object { Write-Host $_ }

Write-Host ""
Write-Host "=== Ribbon-area invokables (y between 400 and 530) ==="
$j.invokables | Where-Object {
    $xy = $_.bounds_xy -split ","
    [int]$xy[1] -ge 400 -and [int]$xy[1] -le 530
} | ForEach-Object {
    "  '" + $_.name + "' [" + $_.controlType + "] xy=" + $_.bounds_xy + " wh=" + $_.bounds_wh
} | ForEach-Object { Write-Host $_ }
