<#
Disposable smoke test for known think-cell UI entrypoints.

This tests whether Office exposes think-cell custom ribbon controls through
CommandBars.ExecuteMso and whether the public UI-only COM methods create any
shape without manual mouse input. It does not save a presentation.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Row {
    param([string] $Name, [string] $Kind)
    [ordered]@{
        name = $Name
        kind = $Kind
        status = "not_run"
        return_value = $null
        elapsed_ms = $null
        shapes_before = $null
        shapes_after = $null
        error = $null
    }
}

function Start-EscapeSender {
    param([int] $DelayMs = 900)
    try {
        Start-Process powershell -WindowStyle Hidden -ArgumentList @(
            "-NoProfile",
            "-Command",
            "Start-Sleep -Milliseconds $DelayMs; try { `$ws = New-Object -ComObject WScript.Shell; `$ws.SendKeys('{ESC}') } catch {}"
        ) | Out-Null
    } catch {}
}

$result = [ordered]@{
    schema = "simcorp-thinkcell-ui-entrypoint-probe/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    tests = @()
    verdict = [ordered]@{}
    errors = @()
}

$ppt = $null
$pres = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $tcPp = $ppt.COMAddIns.Item("thinkcell.addin").Object
    $pres = $ppt.Presentations.Add(-1)
    $slide = $pres.Slides.Add(1, 12) # ppLayoutBlank

    $executeMsoIds = @(
        "tc:ChartsGallery",
        "tc:ElementsGallery",
        "tc:Table",
        "tc:ChartToDataDialog",
        "ChartsGallery",
        "ElementsGallery",
        "ChartToDataDialog"
    )
    foreach ($id in $executeMsoIds) {
        $row = New-Row $id "CommandBars.ExecuteMso"
        try {
            $row.shapes_before = $slide.Shapes.Count
            Start-EscapeSender 700
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $ppt.CommandBars.ExecuteMso($id)
            $sw.Stop()
            Start-Sleep -Milliseconds 300
            $row.status = "returned"
            $row.elapsed_ms = [int] $sw.ElapsedMilliseconds
            $row.shapes_after = $slide.Shapes.Count
        } catch {
            $row.status = "error"
            $row.error = $_.Exception.Message
            try { $row.shapes_after = $slide.Shapes.Count } catch {}
        }
        $result.tests += $row
    }

    $row = New-Row "StartTableInsertion" "tcPpAddIn"
    try {
        $row.shapes_before = $slide.Shapes.Count
        Start-EscapeSender 900
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $rv = $tcPp.StartTableInsertion()
        $sw.Stop()
        Start-Sleep -Milliseconds 500
        $row.status = "returned"
        $row.return_value = if ($null -eq $rv) { $null } else { [string] $rv }
        $row.elapsed_ms = [int] $sw.ElapsedMilliseconds
        $row.shapes_after = $slide.Shapes.Count
    } catch {
        $row.status = "error"
        $row.error = $_.Exception.Message
        try { $row.shapes_after = $slide.Shapes.Count } catch {}
    }
    $result.tests += $row

    $row = New-Row "ShowChartGallery(100,100,700,500,0)" "tcPpAddIn"
    try {
        $row.shapes_before = $slide.Shapes.Count
        Start-EscapeSender 1100
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $rv = $tcPp.ShowChartGallery(100, 100, 700, 500, 0)
        $sw.Stop()
        Start-Sleep -Milliseconds 500
        $row.status = "returned"
        $row.return_value = if ($null -eq $rv) { $null } else { [string] $rv }
        $row.elapsed_ms = [int] $sw.ElapsedMilliseconds
        $row.shapes_after = $slide.Shapes.Count
    } catch {
        $row.status = "error"
        $row.error = $_.Exception.Message
        try { $row.shapes_after = $slide.Shapes.Count } catch {}
    }
    $result.tests += $row

    $created = @($result.tests | Where-Object { $_.shapes_after -gt $_.shapes_before })
    $result.verdict = [ordered]@{
        any_entrypoint_created_shape = @($created).Count -gt 0
        created_shape_tests = @($created | ForEach-Object { $_.name })
        conclusion = if (@($created).Count -gt 0) {
            "A UI entrypoint changed slide shape count. This still needs manual inspection and repair/open smoke before use."
        } else {
            "No tested UI entrypoint created a shape without manual mouse input. Custom ribbon IDs were not executable through ExecuteMso."
        }
    }
} catch {
    $result.errors += [ordered]@{ where = "top_level"; message = $_.Exception.Message }
} finally {
    if ($pres) {
        try { $pres.Saved = -1 } catch {}
        try { $pres.Close() | Out-Null } catch {}
    }
    if ($ppt) {
        try { $ppt.Quit() | Out-Null } catch {}
    }
}

$json = $result | ConvertTo-Json -Depth 8
if ($OutputPath) {
    try {
        $parent = Split-Path -Parent $OutputPath
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)
    } catch {}
}
$json
