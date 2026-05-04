<#
Dynamic trace for think-cell UI creation paths.

This is a disposable trace. It starts a WPR trace if permissions allow, opens
fresh PowerPoint presentations, invokes known UI-only think-cell methods, saves
throwaway PPTX outputs, captures process/module/UIA snapshots, then stops WPR.

The goal is evidence, not production automation. Unknown/internal methods are
not invoked.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-JsonNoBom {
    param([string] $Path, [object] $Object, [int] $Depth = 10)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $json = $Object | ConvertTo-Json -Depth $Depth
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function New-TraceResult {
    [ordered]@{
        schema = "simcorp-thinkcell-ui-dynamic-trace/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        output_dir = $OutputDir
        wpr = [ordered]@{}
        logman = [ordered]@{}
        provider_inventory = @()
        actions = @()
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $ErrorRecord)
    $message = if ($ErrorRecord.Exception) { $ErrorRecord.Exception.Message } else { [string] $ErrorRecord }
    $Result.errors += [ordered]@{ where = $Where; message = $message }
}

function Start-EscapeSender {
    param(
        [int] $DelayMs = 1200,
        [string] $Keys = "{ESC}"
    )
    try {
        $encodedKeys = $Keys.Replace("'", "''")
        Start-Process powershell -WindowStyle Hidden -ArgumentList @(
            "-NoProfile",
            "-Command",
            "Start-Sleep -Milliseconds $DelayMs; try { `$ws = New-Object -ComObject WScript.Shell; `$ws.SendKeys('$encodedKeys') } catch {}"
        ) | Out-Null
    } catch {}
}

function Get-ProcessSnapshot {
    $rows = @()
    try {
        $names = @("POWERPNT", "EXCEL", "ppttc", "ppttchdl", "tcserver", "tcrunxl", "tctabimp", "tcasr", "tcindex")
        foreach ($proc in Get-Process -ErrorAction SilentlyContinue | Where-Object { $names -contains $_.ProcessName }) {
            $startTime = $null
            $path = $null
            $mainWindowTitle = $null
            try { $startTime = $proc.StartTime.ToString("o") } catch {}
            try { $path = $proc.Path } catch {}
            try { $mainWindowTitle = $proc.MainWindowTitle } catch {}
            $row = [ordered]@{
                process_name = $proc.ProcessName
                id = $proc.Id
                start_time = $startTime
                path = $path
                main_window_title = $mainWindowTitle
                modules = @()
            }
            try {
                $row.modules = @(
                    $proc.Modules |
                        Where-Object { $_.ModuleName -match "think|tcaddin|office|mso|powerpnt|ppt" } |
                        Select-Object -First 80 |
                        ForEach-Object {
                            [ordered]@{
                                module_name = $_.ModuleName
                                file_name = $_.FileName
                                base_address = $_.BaseAddress.ToString()
                            }
                        }
                )
            } catch {}
            $rows += $row
        }
    } catch {}
    return $rows
}

function Get-UiSnapshot {
    param([int] $MaxItems = 220)
    $items = @()
    try {
        Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue | Out-Null
        Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue | Out-Null
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
                if ($text -notmatch "(?i)think|cell|chart|table|PowerPoint|gallery|mekko|waterfall|gantt|insert") { continue }
                $rect = $el.Current.BoundingRectangle
                $items += [ordered]@{
                    name = $name
                    class_name = $className
                    automation_id = $automationId
                    control_type = $controlType
                    is_offscreen = [bool] $el.Current.IsOffscreen
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

function Get-PackageSummary {
    param([string] $Pptx)
    $summary = [ordered]@{
        path = $Pptx
        present = $false
        size_bytes = $null
        entries = @()
        ole_count = 0
        chart_count = 0
    }
    if (-not (Test-Path -LiteralPath $Pptx)) { return $summary }
    $summary.present = $true
    $summary.size_bytes = (Get-Item -LiteralPath $Pptx).Length
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue | Out-Null
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Pptx)
        try {
            $summary.entries = @($zip.Entries | ForEach-Object { $_.FullName } | Sort-Object)
            $summary.ole_count = @($summary.entries | Where-Object { $_ -match "embeddings|oleObject" }).Count
            $summary.chart_count = @($summary.entries | Where-Object { $_ -match "ppt/charts/chart" }).Count
        } finally {
            $zip.Dispose()
        }
    } catch {}
    return $summary
}

function Invoke-UiAction {
    param(
        [string] $Name,
        [scriptblock] $Action,
        [string] $OutputDir
    )
    $row = [ordered]@{
        name = $Name
        started_at_utc = [DateTime]::UtcNow.ToString("o")
        status = "unknown"
        return_value = $null
        elapsed_ms = $null
        shapes_before = $null
        shapes_after = $null
        deck_path = $null
        package_summary = [ordered]@{}
        process_before = @()
        process_after = @()
        ui_before = @()
        ui_after = @()
        error = $null
    }

    $ppt = $null
    $pres = $null
    try {
        $ppt = New-Object -ComObject PowerPoint.Application
        $ppt.Visible = -1
        $tcPp = $ppt.COMAddIns.Item("thinkcell.addin").Object
        $pres = $ppt.Presentations.Add(-1)
        $slide = $pres.Slides.Add(1, 12) # ppLayoutBlank
        try { $ppt.ActiveWindow.View.GotoSlide(1) | Out-Null } catch {}

        Start-Sleep -Milliseconds 800
        $row.shapes_before = $slide.Shapes.Count
        $row.process_before = @(Get-ProcessSnapshot)
        $row.ui_before = @(Get-UiSnapshot)

        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $rv = & $Action $ppt $tcPp $pres $slide
        $sw.Stop()
        Start-Sleep -Milliseconds 1000
        Start-EscapeSender 100 "{ESC}"
        Start-Sleep -Milliseconds 300

        $row.status = "returned"
        $row.return_value = if ($null -eq $rv) { $null } else { [string] $rv }
        $row.elapsed_ms = [int] $sw.ElapsedMilliseconds
        $row.shapes_after = $slide.Shapes.Count
        $row.process_after = @(Get-ProcessSnapshot)
        $row.ui_after = @(Get-UiSnapshot)

        $deck = Join-Path $OutputDir "$Name.pptx"
        try {
            $pres.SaveAs($deck)
            $row.deck_path = $deck
            $row.package_summary = Get-PackageSummary $deck
        } catch {
            $row.error = "save failed: $($_.Exception.Message)"
        }
    } catch {
        $row.status = "error"
        $row.error = $_.Exception.Message
        try { if ($slide) { $row.shapes_after = $slide.Shapes.Count } } catch {}
        $row.process_after = @(Get-ProcessSnapshot)
        $row.ui_after = @(Get-UiSnapshot)
    } finally {
        if ($pres) {
            try { $pres.Saved = -1 } catch {}
            try { $pres.Close() | Out-Null } catch {}
        }
        if ($ppt) {
            try { $ppt.Quit() | Out-Null } catch {}
        }
    }
    return $row
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$result = New-TraceResult

try {
    $result.provider_inventory = @(
        & logman query providers 2>$null |
            Where-Object { $_ -match "(?i)office|powerpoint|microsoft-office|com|ole" } |
            Select-Object -First 120
    )
} catch {
    Add-ErrorRow $result "provider_inventory" $_
}

$etl = Join-Path $OutputDir "thinkcell_ui_dynamic_trace.etl"
$logmanEtl = Join-Path $OutputDir "thinkcell_ui_dynamic_trace_logman.etl"
$wprStarted = $false
$logmanStarted = $false
$logmanTraceName = "tc_ui_trace_$PID"
try {
    $startOut = & wpr -start GeneralProfile -filemode 2>&1
    $startCode = $LASTEXITCODE
    $result.wpr.start_exit_code = $startCode
    $result.wpr.start_output = [string]::Join("`n", ($startOut | ForEach-Object { "$_" }))
    $wprStarted = $startCode -eq 0
} catch {
    $result.wpr.start_error = $_.Exception.Message
}

if (-not $wprStarted) {
    try {
        $providers = @(
            "Microsoft-Office-Events",
            "Microsoft-Windows-COM",
            "Microsoft-Windows-COMRuntime",
            "Microsoft-Windows-OLE-Perf",
            "OfficeLoggingLiblet"
        )
        $primaryProvider = $providers[0]
        $logmanArgs = @("create", "trace", $logmanTraceName, "-ow", "-o", $logmanEtl, "-ets", "-p", $primaryProvider, "0xFFFFFFFF", "5")
        $logmanOut = @(& logman @logmanArgs 2>&1)
        $logmanCode = $LASTEXITCODE
        $providerUpdates = @()
        if ($logmanCode -eq 0) {
            foreach ($provider in $providers[1..($providers.Count - 1)]) {
                $updateOut = @(& logman update trace $logmanTraceName -ets -p $provider 0xFFFFFFFF 5 2>&1)
                $providerUpdates += [ordered]@{
                    provider = $provider
                    exit_code = $LASTEXITCODE
                    output = [string]::Join("`n", ($updateOut | ForEach-Object { "$_" }))
                }
            }
        }
        $result.logman.start_exit_code = $logmanCode
        $result.logman.start_output = [string]::Join("`n", ($logmanOut | ForEach-Object { "$_" }))
        $result.logman.provider_updates = $providerUpdates
        $result.logman.trace_name = $logmanTraceName
        $result.logman.providers = $providers
        $logmanStarted = $logmanCode -eq 0
    } catch {
        $result.logman.start_error = $_.Exception.Message
    }
} else {
    $result.logman.start_skipped = "WPR trace started"
}

$result.actions += Invoke-UiAction -Name "start_table_insertion" -OutputDir $OutputDir -Action {
    param($ppt, $tcPp, $pres, $slide)
    Start-EscapeSender 1800 "{ESC}"
    return $tcPp.StartTableInsertion()
}

$result.actions += Invoke-UiAction -Name "show_chart_gallery" -OutputDir $OutputDir -Action {
    param($ppt, $tcPp, $pres, $slide)
    Start-EscapeSender 1800 "{ESC}"
    return $tcPp.ShowChartGallery(100, 100, 700, 500, 0)
}

if ($wprStarted) {
    try {
        $stopOut = & wpr -stop $etl 2>&1
        $stopCode = $LASTEXITCODE
        $result.wpr.stop_exit_code = $stopCode
        $result.wpr.stop_output = [string]::Join("`n", ($stopOut | ForEach-Object { "$_" }))
        $result.wpr.etl_path = $etl
        $result.wpr.etl_present = Test-Path -LiteralPath $etl
        $result.wpr.etl_size_bytes = if (Test-Path -LiteralPath $etl) { (Get-Item -LiteralPath $etl).Length } else { $null }
    } catch {
        $result.wpr.stop_error = $_.Exception.Message
    }
} else {
    $result.wpr.stop_skipped = "WPR did not start"
}

if ($logmanStarted) {
    try {
        $logmanStopOut = & logman stop $logmanTraceName -ets 2>&1
        $logmanStopCode = $LASTEXITCODE
        $result.logman.stop_exit_code = $logmanStopCode
        $result.logman.stop_output = [string]::Join("`n", ($logmanStopOut | ForEach-Object { "$_" }))
        $result.logman.etl_path = $logmanEtl
        $result.logman.etl_present = Test-Path -LiteralPath $logmanEtl
        $result.logman.etl_size_bytes = if (Test-Path -LiteralPath $logmanEtl) { (Get-Item -LiteralPath $logmanEtl).Length } else { $null }
    } catch {
        $result.logman.stop_error = $_.Exception.Message
    }
} else {
    $result.logman.stop_skipped = "logman did not start"
}

try {
    $created = @($result.actions | Where-Object { $_.shapes_after -gt $_.shapes_before })
    $ole = @($result.actions | Where-Object { $_.package_summary.ole_count -gt 0 -or $_.package_summary.chart_count -gt 0 })
    $result.verdict = [ordered]@{
        wpr_trace_created = [bool] $result.wpr.etl_present
        logman_trace_created = [bool] $result.logman.etl_present
        any_ui_action_created_shape = @($created).Count -gt 0
        created_shape_actions = @($created | ForEach-Object { $_.name })
        any_saved_package_has_chart_or_ole = @($ole).Count -gt 0
        package_chart_or_ole_actions = @($ole | ForEach-Object { $_.name })
        conclusion = if (@($created).Count -gt 0) {
            "A UI-only method created a shape in a disposable deck. Inspect the saved package and ETL before any further use."
        } else {
            "The tested UI-only methods did not create a chart/table shape without manual placement. Trace artifacts were still captured where available."
        }
    }
} catch {
    Add-ErrorRow $result "verdict" $_
}

$jsonPath = Join-Path $OutputDir "thinkcell_ui_dynamic_trace.json"
Write-JsonNoBom $jsonPath $result 12
$result | ConvertTo-Json -Depth 12
