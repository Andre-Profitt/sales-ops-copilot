<#
Phase 3 — differential customXml capture for think-cellXML grammar inference.

Method:
- Open a known think-cell deck
- Save baseline (deck A)
- Make ONE programmatic change to a chart (e.g., toggle one property)
- Save modified (deck B)
- Diff customXml/item*.xml + drawings between A and B
- Capture (input description → diff) sample

Repeat across many property changes to build up a grammar corpus.

Output samples land in state/thinkcell_bridge/phase3_xml_grammar/<ts>/samples/.
Each sample directory contains:
  baseline.pptx + modified.pptx
  baseline_customxml/ + modified_customxml/  (extracted XML parts)
  diff.txt
  metadata.json (description of the change)
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
        schema = "simcorp-thinkcell-phase3-xml-diff/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        samples = @()
        errors = @()
    }
}
function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

function Extract-CustomXml {
    param([string] $PptxPath, [string] $OutDir)
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($PptxPath)
    foreach ($e in $zip.Entries) {
        if ($e.FullName -match '^(customXml/|ppt/embeddings/|ppt/slides/_rels/)' -or $e.FullName -match 'thinkcell|tcChart') {
            $dest = Join-Path $OutDir ($e.FullName -replace '/', '_')
            $stream = $e.Open()
            try {
                $fs = [System.IO.File]::OpenWrite($dest)
                $stream.CopyTo($fs)
                $fs.Close()
            } finally { $stream.Close() }
        }
    }
    $zip.Dispose()
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME

if (-not $DeckPath) {
    $candidates = @(
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed.pptx",
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed_charts.pptx"
    )
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { $DeckPath = $c; break } }
}
if (-not $DeckPath -or -not (Test-Path -LiteralPath $DeckPath)) {
    Add-ErrorRow -Result $result -Where "deck" -Err "no deck"
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}

$workRoot = Join-Path $env:TEMP "tcw_xml_diff_$(Get-Random)"
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
$samplesRoot = Join-Path $workRoot "samples"
New-Item -ItemType Directory -Path $samplesRoot -Force | Out-Null

# Sample changes to attempt — each is one property mutation on the first chart shape
$mutations = @(
    @{ tag = "rotation_15"; description = "Rotate first chart by 15 deg"; apply = { param($shape) $shape.Rotation = 15 } },
    @{ tag = "rotation_0";  description = "Reset rotation to 0";          apply = { param($shape) $shape.Rotation = 0 } },
    @{ tag = "left_50";     description = "Set Left = 50";                 apply = { param($shape) $shape.Left = 50 } },
    @{ tag = "left_200";    description = "Set Left = 200";                apply = { param($shape) $shape.Left = 200 } },
    @{ tag = "width_400";   description = "Set Width = 400";               apply = { param($shape) $shape.Width = 400 } },
    @{ tag = "rename_S99";  description = "Rename to ChartS99";            apply = { param($shape) $shape.Name = "ChartS99" } }
)

$ppt = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    foreach ($m in $mutations) {
        $sampleDir = Join-Path $samplesRoot $m.tag
        New-Item -ItemType Directory -Path $sampleDir -Force | Out-Null
        $baseDeck = Join-Path $sampleDir "baseline.pptx"
        $modDeck = Join-Path $sampleDir "modified.pptx"
        Copy-Item -LiteralPath $DeckPath -Destination $baseDeck -Force

        try {
            $pres = $ppt.Presentations.Open($baseDeck, $false, $false, $false)
            # Find first non-text shape on first slide
            $target = $null
            foreach ($shape in $pres.Slides.Item(1).Shapes) {
                $target = $shape; break
            }
            if (-not $target) { throw "no shape on slide 1" }
            $beforePos = [ordered]@{
                left = [double]$target.Left; top = [double]$target.Top
                width = [double]$target.Width; height = [double]$target.Height
                rotation = [double]$target.Rotation; name = [string]$target.Name
            }
            & $m.apply $target
            $pres.SaveAs($modDeck, 24, $false)  # 24 = ppSaveAsOpenXMLPresentation
            $afterPos = [ordered]@{
                left = [double]$target.Left; top = [double]$target.Top
                width = [double]$target.Width; height = [double]$target.Height
                rotation = [double]$target.Rotation; name = [string]$target.Name
            }
            $pres.Close()

            Extract-CustomXml -PptxPath $baseDeck -OutDir (Join-Path $sampleDir "baseline_customxml")
            Extract-CustomXml -PptxPath $modDeck -OutDir (Join-Path $sampleDir "modified_customxml")

            $entry = [ordered]@{
                tag = $m.tag
                description = $m.description
                sample_dir = $sampleDir
                target_shape_id = [int]$target.Id
                target_shape_name = [string]$target.Name
                before = $beforePos
                after = $afterPos
            }
            $metaPath = Join-Path $sampleDir "metadata.json"
            $entry | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $metaPath -Encoding UTF8
            $result.samples += $entry
        } catch {
            Add-ErrorRow -Result $result -Where "mutation:$($m.tag)" -Err $_
        }
    }
} catch {
    Add-ErrorRow -Result $result -Where "main" -Err $_
} finally {
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
}

$result.work_root = $workRoot

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
