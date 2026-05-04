<#
Interactive console probe for think-cell's UI creation path.

This is evidence-only. It runs in the logged-in Windows console session through
a temporary scheduled task, opens a disposable PowerPoint deck, inventories the
Office CommandBars/UIAutomation surfaces, captures screenshots, and optionally
invokes visible controls if they expose a safe InvokePattern.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,
    [switch] $TryInvoke
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-JsonNoBom {
    param([string] $Path, [object] $Object, [int] $Depth = 12)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $json = $Object | ConvertTo-Json -Depth $Depth
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $ErrorRecord)
    $message = if ($ErrorRecord.Exception) { $ErrorRecord.Exception.Message } else { [string] $ErrorRecord }
    $Result.errors += [ordered]@{ where = $Where; message = $message }
}

function Save-ScreenShot {
    param([string] $Path)
    try {
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop | Out-Null
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop | Out-Null
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
            $parent = Split-Path -Parent $Path
            if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
            return [ordered]@{ path = $Path; width = $bounds.Width; height = $bounds.Height; ok = $true }
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    } catch {
        return [ordered]@{ path = $Path; ok = $false; error = $_.Exception.Message }
    }
}

function Get-UiSnapshot {
    param([int] $MaxItems = 600)
    $items = @()
    try {
        Add-Type -AssemblyName UIAutomationClient -ErrorAction Stop | Out-Null
        Add-Type -AssemblyName UIAutomationTypes -ErrorAction Stop | Out-Null
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($el in $all) {
            if ($items.Count -ge $MaxItems) { break }
            try {
                $name = [string] $el.Current.Name
                $className = [string] $el.Current.ClassName
                $automationId = [string] $el.Current.AutomationId
                $controlType = [string] $el.Current.ControlType.ProgrammaticName
                $text = "$name $className $automationId $controlType"
                if ($text -notmatch "(?i)think|cell|chart|table|PowerPoint|gallery|mekko|waterfall|gantt|insert|add-ins|elements|column|bar|line|scatter") { continue }
                $rect = $el.Current.BoundingRectangle
                $patterns = @()
                try { $patterns = @($el.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }) } catch {}
                $items += [ordered]@{
                    name = $name
                    class_name = $className
                    automation_id = $automationId
                    control_type = $controlType
                    is_offscreen = [bool] $el.Current.IsOffscreen
                    is_enabled = [bool] $el.Current.IsEnabled
                    patterns = $patterns
                    rect = [ordered]@{
                        x = [double] $rect.X
                        y = [double] $rect.Y
                        width = [double] $rect.Width
                        height = [double] $rect.Height
                    }
                }
            } catch {}
        }
    } catch {
        $items += [ordered]@{ error = $_.Exception.Message }
    }
    return $items
}

function Get-CommandBarsSnapshot {
    param([object] $Ppt, [int] $MaxControls = 1200)
    $rows = @()
    try {
        foreach ($bar in $Ppt.CommandBars) {
            try {
                $barName = [string] $bar.Name
                $barNameLocal = [string] $bar.NameLocal
                foreach ($control in $bar.Controls) {
                    if ($rows.Count -ge $MaxControls) { return $rows }
                    try {
                        $caption = [string] $control.Caption
                        $tooltip = [string] $control.TooltipText
                        $id = $null
                        $tag = $null
                        $accName = $null
                        try { $id = [string] $control.Id } catch {}
                        try { $tag = [string] $control.Tag } catch {}
                        try { $accName = [string] $control.accName } catch {}
                        $text = "$barName $barNameLocal $caption $tooltip $tag $accName"
                        if ($text -notmatch "(?i)think|cell|chart|table|mekko|waterfall|gantt|timeline|scatter|bubble|elements|insert|add-in") { continue }
                        $rows += [ordered]@{
                            command_bar = $barName
                            command_bar_local = $barNameLocal
                            caption = $caption
                            tooltip = $tooltip
                            id = $id
                            tag = $tag
                            acc_name = $accName
                            type = [string] $control.Type
                            enabled = [bool] $control.Enabled
                            visible = [bool] $control.Visible
                        }
                    } catch {}
                }
            } catch {}
        }
    } catch {
        $rows += [ordered]@{ error = $_.Exception.Message }
    }
    return $rows
}

function Invoke-VisibleElementByName {
    param(
        [string] $NamePattern,
        [int] $DelayMs = 500
    )
    $row = [ordered]@{ pattern = $NamePattern; status = "not_found"; matched = $null; error = $null }
    try {
        Add-Type -AssemblyName UIAutomationClient -ErrorAction Stop | Out-Null
        Add-Type -AssemblyName UIAutomationTypes -ErrorAction Stop | Out-Null
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($el in $all) {
            try {
                if (-not $el.Current.IsEnabled -or $el.Current.IsOffscreen) { continue }
                $name = [string] $el.Current.Name
                $controlType = [string] $el.Current.ControlType.ProgrammaticName
                if ($name -notmatch $NamePattern) { continue }
                $invoke = $null
                $select = $null
                try { $invoke = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern) } catch {}
                try { $select = $el.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern) } catch {}
                if ($null -eq $invoke -and $null -eq $select) { continue }
                $rect = $el.Current.BoundingRectangle
                $row.matched = [ordered]@{
                    name = $name
                    control_type = $controlType
                    rect = [ordered]@{ x = [double] $rect.X; y = [double] $rect.Y; width = [double] $rect.Width; height = [double] $rect.Height }
                }
                if ($null -ne $select) {
                    $select.Select()
                    $row.action = "select"
                } else {
                    $invoke.Invoke()
                    $row.action = "invoke"
                }
                Start-Sleep -Milliseconds $DelayMs
                $row.status = "ok"
                return $row
            } catch {}
        }
    } catch {
        $row.status = "error"
        $row.error = $_.Exception.Message
    }
    return $row
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$result = [ordered]@{
    schema = "simcorp-thinkcell-interactive-ui-path/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    output_dir = $OutputDir
    try_invoke = [bool] $TryInvoke
    session = [ordered]@{}
    powerpoint = [ordered]@{}
    screenshots = @()
    command_bars = @()
    ui_snapshots = [ordered]@{}
    invoked = @()
    package_summary = [ordered]@{}
    verdict = [ordered]@{}
    errors = @()
}

$ppt = $null
$pres = $null
try {
    try {
        $result.session.user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $result.session.session_id = (Get-Process -Id $PID).SessionId
        $result.session.interactive = [Environment]::UserInteractive
    } catch {}

    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    Start-Sleep -Milliseconds 1500
    $pres = $ppt.Presentations.Add(-1)
    $slide = $pres.Slides.Add(1, 12)
    $ppt.ActiveWindow.View.GotoSlide(1) | Out-Null
    try { $ppt.WindowState = 3 } catch {}
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction SilentlyContinue | Out-Null
        [Microsoft.VisualBasic.Interaction]::AppActivate($ppt.Caption) | Out-Null
    } catch {}
    Start-Sleep -Milliseconds 1500

    $result.powerpoint.version = [string] $ppt.Version
    $result.powerpoint.caption = [string] $ppt.Caption
    try {
        $tc = $ppt.COMAddIns.Item("thinkcell.addin")
        $result.powerpoint.thinkcell_addin = [ordered]@{
            description = [string] $tc.Description
            prog_id = [string] $tc.ProgId
            connect = [bool] $tc.Connect
            object_type = if ($tc.Object) { [string] $tc.Object.GetType().FullName } else { $null }
        }
    } catch { Add-ErrorRow $result "thinkcell_addin" $_ }

    $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "01_powerpoint_open.png")
    $result.command_bars = @(Get-CommandBarsSnapshot $ppt)
    $result.ui_snapshots.before = @(Get-UiSnapshot)

    if ($TryInvoke) {
        $result.invoked += Invoke-VisibleElementByName "(?i)^think-cell$" 900
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "02_after_thinkcell_tab.png")
        $result.ui_snapshots.after_thinkcell_tab = @(Get-UiSnapshot)

        $result.invoked += Invoke-VisibleElementByName "(?i)^Elements$|Chart|Column|Bar|Table" 1200
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "03_after_elements_or_chart.png")
        $result.ui_snapshots.after_elements_or_chart = @(Get-UiSnapshot)
    }

    $deck = Join-Path $OutputDir "interactive-ui-probe.pptx"
    try {
        $pres.SaveCopyAs($deck)
        $entries = @()
        $oleCount = 0
        $chartCount = 0
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue | Out-Null
        $zip = [System.IO.Compression.ZipFile]::OpenRead($deck)
        try {
            $entries = @($zip.Entries | ForEach-Object { $_.FullName } | Sort-Object)
            $oleCount = @($entries | Where-Object { $_ -match "embeddings|oleObject" }).Count
            $chartCount = @($entries | Where-Object { $_ -match "ppt/charts/chart" }).Count
        } finally {
            $zip.Dispose()
        }
        $result.package_summary = [ordered]@{
            path = $deck
            size_bytes = (Get-Item -LiteralPath $deck).Length
            shape_count = $slide.Shapes.Count
            ole_count = $oleCount
            chart_count = $chartCount
        }
    } catch { Add-ErrorRow $result "save_package" $_ }

    $visibleThinkCellControls = @($result.ui_snapshots.Values | ForEach-Object { $_ } | Where-Object { $_.name -match "(?i)think|cell|Elements|Chart|Table" -and -not $_.is_offscreen })
    $result.verdict = [ordered]@{
        command_bar_thinkcell_count = @($result.command_bars | Where-Object { $_.caption -match "(?i)think|cell" -or $_.tooltip -match "(?i)think|cell" }).Count
        visible_ui_thinkcell_count = @($visibleThinkCellControls).Count
        shape_count = $slide.Shapes.Count
        package_has_chart_or_ole = ($result.package_summary.ole_count -gt 0 -or $result.package_summary.chart_count -gt 0)
        conclusion = if ($result.package_summary.ole_count -gt 0 -or $result.package_summary.chart_count -gt 0) {
            "Interactive probe produced a package with chart/OLE content. Inspect screenshots and deck before considering this usable."
        } elseif (@($visibleThinkCellControls).Count -gt 0) {
            "Interactive UI exposes think-cell controls, but this probe did not create a chart object."
        } else {
            "Interactive session did not expose an invokable think-cell chart creation path in CommandBars/UIAutomation."
        }
    }
} catch {
    Add-ErrorRow $result "top_level" $_
} finally {
    if ($pres) {
        try { $pres.Saved = -1 } catch {}
        try { $pres.Close() | Out-Null } catch {}
    }
    if ($ppt) {
        try { $ppt.Quit() | Out-Null } catch {}
    }
}

Write-JsonNoBom (Join-Path $OutputDir "thinkcell_interactive_ui_path.json") $result 14
