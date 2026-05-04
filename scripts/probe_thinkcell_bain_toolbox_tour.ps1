<#
BainToolbox programmatic tour.

We now know full signatures via typeinfo:
- BainToolboxRectangles(Slide, safeArrayOfLeftTopWidthHeightMovable, safeArrayOfLeftTopWidthHeightFixed)
- BainToolboxApplyShift(Slide, safeArrayOfOffsets)

Hypothesis (from agent intel about COIN-OR CLP solver in tcaddin): these
methods solve a shape-packing LP — movable shapes are positioned to avoid
fixed shapes. Confirming this gives us a free slide-arrangement automation
lane orthogonal to chart automation.

This probe creates a *transient* presentation, places known shapes, calls
both methods, and observes shape positions before/after.

Mutates a transient deck. Closes it without saving. Does not touch any
SimCorp asset.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-bain-toolbox-tour-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        rectangles_test = [ordered]@{}
        applyshift_test = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

function Capture-Shapes {
    param([object] $Slide)
    $entries = @()
    foreach ($shape in $Slide.Shapes) {
        $entries += [ordered]@{
            id = $shape.Id
            name = $shape.Name
            type = [int]$shape.Type
            left = [double]$shape.Left
            top = [double]$shape.Top
            width = [double]$shape.Width
            height = [double]$shape.Height
        }
    }
    return $entries
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

$ppt = $null
$pres = $null
$tcPp = $null

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $a = $ppt.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if (-not $a) {
        Add-ErrorRow -Result $result -Where "addin" -Err "thinkcell.addin not found"
        throw "thinkcell.addin not found"
    }
    $tcPp = $a.Object
    $pres = $ppt.Presentations.Add($false)  # WithWindow=False (try; some builds error here)
    $slide = $pres.Slides.Add(1, 1)  # ppLayoutTitle = 1; arbitrary

    # Add 5 rectangles: 3 "movable", 2 "fixed"
    # msoShapeRectangle = 1
    $shapes = @()
    $shapes += $slide.Shapes.AddShape(1, 50, 50, 100, 80)    # movable 1
    $shapes += $slide.Shapes.AddShape(1, 200, 50, 100, 80)   # movable 2
    $shapes += $slide.Shapes.AddShape(1, 350, 50, 100, 80)   # movable 3
    $shapes += $slide.Shapes.AddShape(1, 100, 200, 200, 80)  # fixed 1
    $shapes += $slide.Shapes.AddShape(1, 400, 200, 100, 80)  # fixed 2

    $beforePositions = Capture-Shapes -Slide $slide
    $result.rectangles_test.before = $beforePositions

    # Build the safe-arrays.
    # Per typeinfo signature: safeArrayOfLeftTopWidthHeightMovable + safeArrayOfLeftTopWidthHeightFixed.
    # Convention guess: each entry is a 4-element array [Left, Top, Width, Height].
    $movable = @(
        ,@([double]$shapes[0].Left, [double]$shapes[0].Top, [double]$shapes[0].Width, [double]$shapes[0].Height),
        ,@([double]$shapes[1].Left, [double]$shapes[1].Top, [double]$shapes[1].Width, [double]$shapes[1].Height),
        ,@([double]$shapes[2].Left, [double]$shapes[2].Top, [double]$shapes[2].Width, [double]$shapes[2].Height)
    )
    $fixed = @(
        ,@([double]$shapes[3].Left, [double]$shapes[3].Top, [double]$shapes[3].Width, [double]$shapes[3].Height),
        ,@([double]$shapes[4].Left, [double]$shapes[4].Top, [double]$shapes[4].Width, [double]$shapes[4].Height)
    )

    # Variant 1 attempt: pass nested arrays
    $variant_results = @()
    $attempts = @(
        @{ tag = "nested_arrays_4tuples"; movable = $movable; fixed = $fixed },
        @{ tag = "flat_array_4tuples"; movable = (,@($movable[0][0], $movable[0][1], $movable[0][2], $movable[0][3], $movable[1][0], $movable[1][1], $movable[1][2], $movable[1][3], $movable[2][0], $movable[2][1], $movable[2][2], $movable[2][3])); fixed = (,@($fixed[0][0], $fixed[0][1], $fixed[0][2], $fixed[0][3], $fixed[1][0], $fixed[1][1], $fixed[1][2], $fixed[1][3])) }
    )
    foreach ($att in $attempts) {
        $rec = [ordered]@{ tag = $att.tag; success = $false; error = $null; hresult = $null }
        try {
            $tcPp.BainToolboxRectangles($slide, $att.movable, $att.fixed)
            $rec.success = $true
        } catch [System.Runtime.InteropServices.COMException] {
            $rec.hresult = "0x" + $_.Exception.HResult.ToString("X8")
            $rec.error = $_.Exception.Message
        } catch [System.Reflection.TargetInvocationException] {
            $rec.hresult = if ($_.Exception.InnerException) { "0x" + $_.Exception.InnerException.HResult.ToString("X8") } else { $null }
            $rec.error = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
        } catch {
            $rec.error = $_.Exception.GetType().Name + ": " + $_.Exception.Message
        }
        $variant_results += $rec
        if ($rec.success) { break }
    }
    $result.rectangles_test.attempts = $variant_results
    $result.rectangles_test.after = Capture-Shapes -Slide $slide

    # ApplyShift attempt: 3 offsets (one per shape), simple [dx, dy] pair each
    $offsets = @(
        ,@([double]10.0, [double]20.0),
        ,@([double]-5.0, [double]15.0),
        ,@([double]0.0, [double]30.0)
    )
    $rec = [ordered]@{ tag = "nested_2tuples"; success = $false; error = $null; hresult = $null }
    try {
        $tcPp.BainToolboxApplyShift($slide, $offsets)
        $rec.success = $true
    } catch [System.Runtime.InteropServices.COMException] {
        $rec.hresult = "0x" + $_.Exception.HResult.ToString("X8")
        $rec.error = $_.Exception.Message
    } catch [System.Reflection.TargetInvocationException] {
        $rec.hresult = if ($_.Exception.InnerException) { "0x" + $_.Exception.InnerException.HResult.ToString("X8") } else { $null }
        $rec.error = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
    } catch {
        $rec.error = $_.Exception.GetType().Name + ": " + $_.Exception.Message
    }
    $result.applyshift_test.attempt = $rec
    $result.applyshift_test.after = Capture-Shapes -Slide $slide

} catch {
    Add-ErrorRow -Result $result -Where "main" -Err $_
} finally {
    if ($pres) { try { $pres.Close() } catch {} }
    if ($tcPp) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcPp) | Out-Null } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
}

$result.verdict.rectangles_succeeded = ($result.rectangles_test.attempts | Where-Object { $_.success }).Count -gt 0
$result.verdict.applyshift_succeeded = ($result.applyshift_test.attempt.success -eq $true)
$result.verdict.shape_positions_changed = $false
if ($result.rectangles_test.before -and $result.rectangles_test.after) {
    for ($i = 0; $i -lt [Math]::Min($result.rectangles_test.before.Count, $result.rectangles_test.after.Count); $i++) {
        $b = $result.rectangles_test.before[$i]
        $a = $result.rectangles_test.after[$i]
        if ($b.left -ne $a.left -or $b.top -ne $a.top) { $result.verdict.shape_positions_changed = $true; break }
    }
}

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
