<#
PowerPoint Shape.Tag enumeration probe.

KB0073 (per the wayback agent finding) documents a `thinkcellShapeDoNotDelete`
shape tag. PowerPoint's Shape.Tags collection is a non-COM key/value store
hung off each shape — readable through pure PowerPoint API without invoking
tcaddin at all.

This probe opens a known think-cell deck (read-only copy), walks every shape
on every slide, and dumps:
- Every (tag name, tag value) pair on every shape that has tags
- Aggregated unique tag names across the whole deck
- Per-tag-name occurrence count

This reveals the full schema of metadata think-cell writes onto shapes —
chart name binding, datasheet ID, automation key, style ID, etc.

Read-only. Opens a copy of the deck (not the original).
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [string] $DeckPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-shape-tags-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        deck_path = $null
        deck_copy = $null
        slide_count = 0
        shape_count = 0
        shapes_with_tags = 0
        tag_pairs = @()
        tag_name_counts = [ordered]@{}
        tag_name_value_samples = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

# Default to a known think-cell donor deck if not provided
if (-not $DeckPath) {
    $candidates = @(
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed.pptx",
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed_charts.pptx",
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_seed_thinkcell.pptx"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { $DeckPath = $c; break }
    }
}
if (-not $DeckPath -or -not (Test-Path -LiteralPath $DeckPath)) {
    Add-ErrorRow -Result $result -Where "deck_resolution" -Err "no readable deck found"
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}
$result.deck_path = $DeckPath

# Copy to a local temp file (don't open the original)
$tempDir = Join-Path $env:TEMP "tcw_shape_tags_$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$copy = Join-Path $tempDir (Split-Path -Leaf $DeckPath)
Copy-Item -LiteralPath $DeckPath -Destination $copy -Force
$result.deck_copy = $copy

$ppt = $null
$pres = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open($copy, $true, $true, $false)  # ReadOnly=True, Untitled=True, WithWindow=False
    $result.slide_count = $pres.Slides.Count

    foreach ($slide in $pres.Slides) {
        foreach ($shape in $slide.Shapes) {
            $result.shape_count++
            $tagCount = 0
            try { $tagCount = $shape.Tags.Count } catch {}
            if ($tagCount -gt 0) {
                $result.shapes_with_tags++
                for ($i = 1; $i -le $tagCount; $i++) {
                    try {
                        $tname = $shape.Tags.Name($i)
                        $tval = $shape.Tags.Value($i)
                        $valSample = if ($tval) { $tval.Substring(0, [Math]::Min(200, $tval.Length)) } else { "" }
                        $result.tag_pairs += [ordered]@{
                            slide_index = $slide.SlideIndex
                            shape_id = $shape.Id
                            shape_name = $shape.Name
                            shape_type = [int]$shape.Type
                            tag_name = $tname
                            tag_value_len = if ($tval) { $tval.Length } else { 0 }
                            tag_value = $valSample
                        }
                        if (-not $result.tag_name_counts.Contains($tname)) {
                            $result.tag_name_counts[$tname] = 0
                            $result.tag_name_value_samples[$tname] = @()
                        }
                        $result.tag_name_counts[$tname]++
                        if ($result.tag_name_value_samples[$tname].Count -lt 3) {
                            $result.tag_name_value_samples[$tname] += $valSample
                        }
                    } catch {
                        Add-ErrorRow -Result $result -Where "tag_read:slide=$($slide.SlideIndex):shape=$($shape.Id):i=$i" -Err $_
                    }
                }
            }
        }
    }
} catch {
    Add-ErrorRow -Result $result -Where "open_or_walk" -Err $_
} finally {
    if ($pres) { try { $pres.Close() } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
    try { Remove-Item -LiteralPath $tempDir -Recurse -Force } catch {}
}

$result.verdict.unique_tag_names = @($result.tag_name_counts.Keys | Sort-Object)
$result.verdict.unique_tag_name_count = @($result.tag_name_counts.Keys).Count
$result.verdict.tagged_shape_pct = if ($result.shape_count -gt 0) { [math]::Round($result.shapes_with_tags * 100.0 / $result.shape_count, 1) } else { 0 }
$result.verdict.has_donotdelete = $result.tag_name_counts.Contains("THINKCELLSHAPEDONOTDELETE")
$result.verdict.thinkcell_tag_names = @($result.tag_name_counts.Keys | Where-Object { $_ -match "(?i)think|tc[._-]" })

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
