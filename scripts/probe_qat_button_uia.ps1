<#
Stage 3 verification — find the pinned tc:AISidePane button on the QAT via UIA.

After probe_qat_pin_aisidepane.ps1 has injected idQ='tc:AISidePane' into
PowerPoint.officeUI's QAT documentControls, launching PP should make the
button appear in the Quick Access Toolbar. QAT items are standard UIA Buttons
regardless of the underlying ribbon control type, so InvokePattern should
work.

This probe walks PP's UIA tree (control view + raw view) looking for ANY
element whose name/automation-id matches AI / Copilot / SidePane patterns,
filtered to those near the top of the window where the QAT lives. Outputs
JSON with all candidates and their bounds.
#>
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient

$out = "$env:USERPROFILE\tc_qat_button.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    pp_pid = $null
    candidates = @()
    qat_items = @()
    errors = @()
}

$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    $result.errors += "no PP with MainWindowTitle"
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.pp_pid = $pp.Id
$result.pp_title = $pp.MainWindowTitle

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }
"@
[void] [W]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 800

$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pp.Id
)
$ppWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)

# Walk in RAW view (Stage 1 lessons learned). The QAT items SHOULD be in
# the control view, but use raw to be safe.
$walker = [System.Windows.Automation.TreeWalker]::RawViewWalker

function Walk {
    param($element, [int]$depth, [int]$maxDepth)
    if ($depth -gt $maxDepth) { return }
    try {
        $name = $element.Current.Name
        $autoId = $element.Current.AutomationId
        $ctrl = $element.Current.ControlType.LocalizedControlType
        $bounds = $element.Current.BoundingRectangle
        $isOff = $element.Current.IsOffscreen
        $patterns = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })

        # AI candidate match
        if (-not $isOff -and ($name -or $autoId) -and (
            $name -match "(?i)\bAI\b|copilot|side ?pane|chart from ai|smart" -or
            $autoId -match "(?i)AISidePane|copilot|smart"
        )) {
            $script:result.candidates += [ordered]@{
                depth = $depth
                name = $name
                automationId = $autoId
                controlType = $ctrl
                bounds_xy = "$([int]$bounds.X),$([int]$bounds.Y)"
                bounds_wh = "$([int]$bounds.Width)x$([int]$bounds.Height)"
                patterns = ($patterns | ForEach-Object { ($_ -replace "PatternIdentifiers.Pattern$", "") })
                isEnabled = $element.Current.IsEnabled
            }
        }
        # QAT items: heuristic — top of window (Y < 200), small (W<60), name set
        if (-not $isOff -and $bounds.Y -lt 220 -and $bounds.Height -lt 80 -and $bounds.Width -gt 8 -and $bounds.Width -lt 100 -and $name) {
            $script:result.qat_items += [ordered]@{
                name = $name
                automationId = $autoId
                controlType = $ctrl
                bounds_xy = "$([int]$bounds.X),$([int]$bounds.Y)"
                bounds_wh = "$([int]$bounds.Width)x$([int]$bounds.Height)"
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
foreach ($w in $ppWindows) { Walk -element $w -depth 0 -maxDepth 18 }

$result.candidate_count = $result.candidates.Count
$result.qat_item_count = $result.qat_items.Count
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $out -Force
Write-Host "QAT button probe: $($result.candidate_count) AI candidates, $($result.qat_item_count) top-band QAT items -> $out"
