<#
Try CommandBars.ExecuteMso("tc:AISidePane") with the think-cell ribbon
tab selected + a blank deck open. Earlier test had neither precondition.

Run via scheduled task in Session 1 (PowerPoint COM needs interactive desktop).
Output: $env:USERPROFILE\tc_aisidepane_test.json
#>
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient

$result = [ordered]@{
    schema = "tc-aisidepane-test/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    session_id = (Get-Process -PID $PID).SessionId
    interactive = [System.Environment]::UserInteractive
    steps = @()
    errors = @()
}

function Step($label, $action) {
    $entry = [ordered]@{ step = $label; ok = $true; note = "" }
    try {
        $r = & $action
        if ($r) { $entry.note = ($r -join " | ").Substring(0, [Math]::Min(300, ($r -join " | ").Length)) }
    } catch {
        $entry.ok = $false
        $entry.note = $_.Exception.Message.Substring(0, [Math]::Min(300, $_.Exception.Message.Length))
        $script:result.errors += [ordered]@{ step = $label; message = $_.Exception.Message }
    }
    $script:result.steps += $entry
}

# 1. Get running PowerPoint via COM (don't launch a new one)
$ppt = $null
Step "get_powerpoint_com" {
    $ppt = [System.Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application")
    "got PowerPoint via GetActiveObject"
}
$ppt = [System.Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application")

# 2. Confirm a presentation is open
Step "presentation_count" {
    "$($ppt.Presentations.Count) presentations open"
}
if ($ppt.Presentations.Count -eq 0) {
    Step "open_blank_deck" {
        $pres = $ppt.Presentations.Add(-1)  # msoTrue: with window
        "opened blank deck: $($pres.Name)"
    }
}

# 3. Connect think-cell add-in
Step "connect_thinkcell_addin" {
    $tc = $ppt.COMAddIns.Item("thinkcell.addin")
    if (-not $tc.Connect) { $tc.Connect = $true }
    "connected: $($tc.Connect)"
}

# 4. Select the think-cell ribbon tab via UIA (so AISidePane idMso resolves)
Step "select_thinkcell_tab" {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "think-cell"
    )
    $tab = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if (-not $tab) { throw "think-cell tab not found in UIA tree" }
    if ($tab.Current.ControlType.LocalizedControlType -ne "tab item") {
        throw "found 'think-cell' but type is $($tab.Current.ControlType.LocalizedControlType)"
    }
    $sel = $tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    $sel.Select()
    Start-Sleep -Milliseconds 800
    "selected think-cell tab"
}

# 5. Now check if tc:AISidePane is enabled/visible
Step "check_aisidepane_state" {
    $vis = $ppt.CommandBars.GetVisibleMso("tc:AISidePane")
    $en = $ppt.CommandBars.GetEnabledMso("tc:AISidePane")
    "visible=$vis enabled=$en"
}

# 6. Try ExecuteMso
Step "execute_aisidepane" {
    $ppt.CommandBars.ExecuteMso("tc:AISidePane")
    Start-Sleep -Seconds 2
    "ExecuteMso returned without throwing"
}

# 7. Check whether the AI side pane is now visible (look for new windows / panels)
Step "post_execute_uia" {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ppt.HWND.ToInt32()
    ) -ErrorAction SilentlyContinue
    # Just enumerate all top-level windows of POWERPNT, see if a new pane appeared
    $procIds = (Get-Process POWERPNT -ErrorAction SilentlyContinue | ForEach-Object Id)
    $newWindows = @()
    foreach ($pid in $procIds) {
        $cond2 = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pid
        )
        $found = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond2)
        foreach ($w in $found) {
            $newWindows += [ordered]@{
                pid = $pid
                name = $w.Current.Name
                controlType = $w.Current.ControlType.LocalizedControlType
                bounds = $w.Current.BoundingRectangle.ToString()
            }
        }
    }
    $script:result.post_execute_windows = $newWindows
    "found $($newWindows.Count) windows after ExecuteMso"
}

$result.ended_utc = [DateTime]::UtcNow.ToString("o")
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$env:USERPROFILE\tc_aisidepane_test.json" -Force
Write-Host "Wrote $env:USERPROFILE\tc_aisidepane_test.json"
