<#
Walk the PowerPoint UIA tree (in Session 1) and report any AI-related
ribbon controls (Name / AutomationId / ControlType / Bounds).

This is the discovery step before scripting an AI button click. Run via
scheduled task in Session 1 because:
- UIA from Session 0 (SSH) cannot see Session 1 windows
- think-cell ribbon tab needs to be expanded for its controls to be in
  the UIA tree

Pre-condition:
- PowerPoint already running with a blank deck (think-cell ribbon visible)

Output: $env:USERPROFILE\tc_uia_discovery.json
#>
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$result = [ordered]@{
    schema = "tc-uia-discovery/v1"
    started_utc = [DateTime]::UtcNow.ToString("o")
    session_id = (Get-Process -PID $PID).SessionId
    interactive = [System.Environment]::UserInteractive
    pp_processes = @()
    pp_windows = @()
    ribbon_tabs = @()
    matching_controls = @()
    errors = @()
}

# Enumerate PowerPoint processes + their main windows
$ppProcs = Get-Process POWERPNT -ErrorAction SilentlyContinue
foreach ($p in $ppProcs) {
    $result.pp_processes += [ordered]@{
        pid = $p.Id
        title = $p.MainWindowTitle
        handle = $p.MainWindowHandle.ToInt64()
    }
}

if ($ppProcs.Count -eq 0) {
    $result.errors += [ordered]@{ where = "process_lookup"; message = "No POWERPNT.EXE running" }
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$env:USERPROFILE\tc_uia_discovery.json" -Force
    exit 1
}

$root = [System.Windows.Automation.AutomationElement]::RootElement
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

# Find PowerPoint top-level windows for ALL POWERPNT pids (the foreground one
# may be the second/third process — the first is often a headless child).
$ppWindows = @()
foreach ($p in $ppProcs) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
        $p.Id
    )
    $found = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
    foreach ($w in $found) { $ppWindows += $w }
}
foreach ($w in $ppWindows) {
    $result.pp_windows += [ordered]@{
        name = $w.Current.Name
        controlType = $w.Current.ControlType.LocalizedControlType
        automationId = $w.Current.AutomationId
        bounds = $w.Current.BoundingRectangle.ToString()
        processId = $w.Current.ProcessId
    }
}

if ($ppWindows.Count -eq 0) {
    $result.errors += [ordered]@{
        where = "window_lookup"
        message = "no PowerPoint windows under desktop root across $($ppProcs.Count) POWERPNT pids: $(($ppProcs | ForEach-Object Id) -join ',')"
    }
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$env:USERPROFILE\tc_uia_discovery.json" -Force
    exit 2
}

# Walk the PowerPoint tree, collect every control whose name or automation id
# matches an AI-pattern. Bounded to depth 8 to avoid infinite descent.
$pattern = "(?i)\b(ai|smart|copilot|suggest|generate|prompt|chat|llm|completion|complete|tcai|text manipulation|tcaddin)\b"
$ribbonHints = "(?i)(ribbon|tab|think-?cell|tc:|tcaddin)"

function Walk-Tree {
    param($element, $depth, $maxDepth)
    if ($depth -gt $maxDepth) { return }

    try {
        $name = $element.Current.Name
        $autoId = $element.Current.AutomationId
        $ctrl = $element.Current.ControlType.LocalizedControlType
        $combined = "$name | $autoId"
        if ($combined -match $pattern -or $autoId -match "^tc:") {
            $bounds = $element.Current.BoundingRectangle
            $script:result.matching_controls += [ordered]@{
                depth = $depth
                name = $name
                automationId = $autoId
                controlType = $ctrl
                bounds = "$($bounds.X),$($bounds.Y),$($bounds.Width)x$($bounds.Height)"
                isEnabled = $element.Current.IsEnabled
                isOffscreen = $element.Current.IsOffscreen
                hasInvoke = $null -ne ($element.GetSupportedPatterns() | Where-Object { $_.ProgrammaticName -eq "InvokePatternIdentifiers.Pattern" })
            }
        }
        if ($combined -match $ribbonHints -and $name) {
            $script:result.ribbon_tabs += [ordered]@{
                depth = $depth
                name = $name
                automationId = $autoId
                controlType = $ctrl
            }
        }
    } catch {}

    # Recurse into children
    try {
        $child = $script:walker.GetFirstChild($element)
        while ($null -ne $child) {
            Walk-Tree -element $child -depth ($depth + 1) -maxDepth $maxDepth
            $child = $script:walker.GetNextSibling($child)
        }
    } catch {}
}

foreach ($win in $ppWindows) {
    Walk-Tree -element $win -depth 0 -maxDepth 8
}

# ----- Find + select the think-cell tab to expose its ribbon controls -----
$tcTab = $null
foreach ($win in $ppWindows) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "think-cell"
    )
    $candidate = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($candidate -and $candidate.Current.ControlType.LocalizedControlType -eq "tab item") {
        $tcTab = $candidate
        break
    }
}

if ($tcTab) {
    $result.thinkcell_tab_found = $true
    $result.thinkcell_tab_bounds = $tcTab.Current.BoundingRectangle.ToString()
    # SelectionItemPattern is the standard way to switch ribbon tabs
    try {
        $selPattern = $tcTab.GetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern
        )
        $selPattern.Select()
        $result.thinkcell_tab_selected = $true
    } catch {
        $result.errors += [ordered]@{ where = "select_thinkcell_tab"; message = $_.Exception.Message }
        # Fallback: try InvokePattern
        try {
            $invPattern = $tcTab.GetCurrentPattern(
                [System.Windows.Automation.InvokePattern]::Pattern
            )
            $invPattern.Invoke()
            $result.thinkcell_tab_invoked = $true
        } catch {
            $result.errors += [ordered]@{ where = "invoke_thinkcell_tab"; message = $_.Exception.Message }
        }
    }
    Start-Sleep -Milliseconds 800

    # Re-walk after selection to pick up newly-exposed think-cell ribbon controls
    $result.matching_controls_post_select = @()
    function Walk-Tree-Post {
        param($element, $depth, $maxDepth)
        if ($depth -gt $maxDepth) { return }
        try {
            $name = $element.Current.Name
            $autoId = $element.Current.AutomationId
            $ctrl = $element.Current.ControlType.LocalizedControlType
            $combined = "$name | $autoId"
            $patternMatch = $combined -match "(?i)\b(ai|smart|copilot|suggest|generate|prompt|chat|llm|completion|complete|tcai|text manipulation|tcaddin|insight|gpt|brain)\b"
            $autoIdMatch = $autoId -match "^tc:"
            if ($patternMatch -or $autoIdMatch) {
                $bounds = $element.Current.BoundingRectangle
                $supported = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
                $script:result.matching_controls_post_select += [ordered]@{
                    depth = $depth
                    name = $name
                    automationId = $autoId
                    controlType = $ctrl
                    bounds = "$($bounds.X),$($bounds.Y),$($bounds.Width)x$($bounds.Height)"
                    isEnabled = $element.Current.IsEnabled
                    isOffscreen = $element.Current.IsOffscreen
                    supportedPatterns = $supported
                }
            }
        } catch {}
        try {
            $child = $script:walker.GetFirstChild($element)
            while ($null -ne $child) {
                Walk-Tree-Post -element $child -depth ($depth + 1) -maxDepth $maxDepth
                $child = $script:walker.GetNextSibling($child)
            }
        } catch {}
    }
    foreach ($win in $ppWindows) {
        Walk-Tree-Post -element $win -depth 0 -maxDepth 12
    }

    # Also: enumerate ALL buttons under the think-cell ribbon (regardless of name)
    # so we can see every clickable thing think-cell exposes
    $result.thinkcell_ribbon_buttons = @()
    foreach ($win in $ppWindows) {
        $btnCond = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::Button
        )
        $allBtns = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
        foreach ($btn in $allBtns) {
            try {
                if (-not $btn.Current.IsOffscreen -and $btn.Current.IsEnabled) {
                    $result.thinkcell_ribbon_buttons += [ordered]@{
                        name = $btn.Current.Name
                        automationId = $btn.Current.AutomationId
                        bounds = $btn.Current.BoundingRectangle.ToString()
                    }
                }
            } catch {}
        }
    }
} else {
    $result.thinkcell_tab_found = $false
}

$result.ended_utc = [DateTime]::UtcNow.ToString("o")
$result.matching_count = $result.matching_controls.Count
$result.tab_count = $result.ribbon_tabs.Count
$result.matching_count_post_select = if ($result.matching_controls_post_select) { $result.matching_controls_post_select.Count } else { 0 }
$result.thinkcell_button_count = if ($result.thinkcell_ribbon_buttons) { $result.thinkcell_ribbon_buttons.Count } else { 0 }

$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath "$env:USERPROFILE\tc_uia_discovery.json" -Force

# Brief stdout summary
Write-Host "session=$($result.session_id) interactive=$($result.interactive)"
Write-Host "powerpnt processes: $($result.pp_processes.Count)"
Write-Host "powerpnt windows:   $($result.pp_windows.Count)"
Write-Host "ribbon-hint controls (showing first 10):"
$result.ribbon_tabs | Select-Object -First 10 | ForEach-Object {
    Write-Host "  [$($_.depth)] $($_.controlType): $($_.name)  (autoId=$($_.automationId))"
}
Write-Host "AI-pattern matches (showing first 20):"
$result.matching_controls | Select-Object -First 20 | ForEach-Object {
    Write-Host "  [$($_.depth)] $($_.controlType): $($_.name)  (autoId=$($_.automationId))"
}
Write-Host "Result JSON: $env:USERPROFILE\tc_uia_discovery.json"
