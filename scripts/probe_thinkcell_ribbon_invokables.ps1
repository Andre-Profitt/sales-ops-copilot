<#
After selecting the think-cell tab, dump EVERY UIA element under the
PowerPoint window that supports InvokePattern OR LegacyIAccessiblePattern,
regardless of ControlType. The AI button must be one of them — we just
need to identify it by Name to know what to click.
#>
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Windows.Forms

$out = "$env:USERPROFILE\tc_invokables.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    pp_pids = @()
    invokables = @()
    errors = @()
}

# Find PowerPoint with a window
$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    $result.errors += [ordered]@{ where = "find_pp"; message = "no PP with MainWindowTitle" }
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.pp_pids = @($pp.Id)
$result.pp_title = $pp.MainWindowTitle

# Foreground PowerPoint
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }
"@
[void] [W]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 500

# Select think-cell tab
$root = [System.Windows.Automation.AutomationElement]::RootElement
$walker = [System.Windows.Automation.TreeWalker]::RawViewWalker  # raw view shows Office Fluent UI items that ControlView filters out
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pp.Id
)
$ppWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)

$tcCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "think-cell"
)
foreach ($w in $ppWindows) {
    $tab = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $tcCond)
    if ($tab -and $tab.Current.ControlType.LocalizedControlType -eq "tab item") {
        try {
            $sel = $tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            $sel.Select()
            $result.tab_selected = $true
            break
        } catch {
            $result.errors += [ordered]@{ where = "select_tab"; message = $_.Exception.Message }
        }
    }
}
Start-Sleep -Milliseconds 1500

# Walk EVERY descendant. Dump anything with InvokePattern or LegacyIAccessiblePattern.
function Walk {
    param($element, $depth, $maxDepth)
    if ($depth -gt $maxDepth) { return }
    try {
        $name = $element.Current.Name
        $autoId = $element.Current.AutomationId
        $ctrl = $element.Current.ControlType.LocalizedControlType
        $bounds = $element.Current.BoundingRectangle
        $patterns = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
        $hasInvoke = $patterns -contains "InvokePatternIdentifiers.Pattern"
        $hasLegacy = $patterns -contains "LegacyIAccessiblePatternIdentifiers.Pattern"
        if (($hasInvoke -or $hasLegacy) -and $name -and -not $element.Current.IsOffscreen) {
            $script:result.invokables += [ordered]@{
                depth = $depth
                name = $name
                automationId = $autoId
                controlType = $ctrl
                bounds_xy = "$([int]$bounds.X),$([int]$bounds.Y)"
                bounds_wh = "$([int]$bounds.Width)x$([int]$bounds.Height)"
                hasInvoke = $hasInvoke
                hasLegacy = $hasLegacy
                isEnabled = $element.Current.IsEnabled
            }
        }
    } catch {}
    try {
        $child = $script:walker.GetFirstChild($element)
        while ($null -ne $child) {
            Walk -element $child -depth ($depth + 1) -maxDepth $maxDepth
            $child = $script:walker.GetNextSibling($child)
        }
    } catch {}
}
foreach ($w in $ppWindows) { Walk -element $w -depth 0 -maxDepth 16 }

$result.invokable_count = $result.invokables.Count
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $out -Force
Write-Host "Dumped $($result.invokable_count) invokables to $out"
