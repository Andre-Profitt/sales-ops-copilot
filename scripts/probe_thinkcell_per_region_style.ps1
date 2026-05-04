<#
LoadStyleForRegion per-region styling probe.

Now-known signature: LoadStyleForRegion(CustomLayout, FileName, Left, Top,
Width, Height). Public docs do not document the 4 region params. This
probe tests:
- Does it actually accept the region params?
- Does the style apply only within that rectangle, or to the whole layout?
- What HRESULT for invalid regions (off-slide, zero-area, negative)?

Mutates a transient layout. Closes deck without saving.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-per-region-style-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        style_files_found = @()
        chosen_style_file = $null
        region_attempts = @()
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

# Locate a style file
$styleRoots = @(
    "C:\Program Files (x86)\think-cell\styles",
    "C:\Program Files\think-cell\styles"
)
foreach ($r in $styleRoots) {
    if (-not (Test-Path -LiteralPath $r)) { continue }
    try {
        $files = Get-ChildItem -LiteralPath $r -Recurse -File -ErrorAction Stop |
            Where-Object { $_.Name -match '\.(xml|tcstyle)$' } | Select-Object -First 20
        foreach ($f in $files) {
            $result.style_files_found += [ordered]@{ path = $f.FullName; size = $f.Length }
        }
    } catch { Add-ErrorRow -Result $result -Where "style_scan:$r" -Err $_ }
}

if ($result.style_files_found.Count -eq 0) {
    Add-ErrorRow -Result $result -Where "style_files" -Err "no style files found in $($styleRoots -join ',')"
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}
$result.chosen_style_file = $result.style_files_found[0].path

$ppt = $null
$pres = $null
$tcPp = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $a = $ppt.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if (-not $a) { Add-ErrorRow -Result $result -Where "addin" -Err "thinkcell.addin missing"; throw "no addin" }
    $tcPp = $a.Object
    $pres = $ppt.Presentations.Add($false)
    # Use the first SlideMaster's first CustomLayout as the target
    $master = $pres.SlideMaster
    $layout = $master.CustomLayouts.Item(1)

    # Try multiple region shapes
    $regionAttempts = @(
        @{ tag = "small_top_left";   left =  50.0; top =  50.0; width = 200.0; height = 100.0 },
        @{ tag = "full_slide";       left =   0.0; top =   0.0; width = 720.0; height = 540.0 },
        @{ tag = "zero_area";        left = 100.0; top = 100.0; width =   0.0; height =   0.0 },
        @{ tag = "negative_offset";  left = -100.0; top = -100.0; width = 200.0; height = 100.0 },
        @{ tag = "way_offscreen";    left = 5000.0; top = 5000.0; width = 200.0; height = 100.0 }
    )

    foreach ($att in $regionAttempts) {
        $rec = [ordered]@{
            tag = $att.tag
            args = [ordered]@{ left = $att.left; top = $att.top; width = $att.width; height = $att.height }
            success = $false
            error = $null
            hresult = $null
            style_name_after = $null
        }
        try {
            $tcPp.LoadStyleForRegion($layout, $result.chosen_style_file, $att.left, $att.top, $att.width, $att.height)
            $rec.success = $true
            try { $rec.style_name_after = $tcPp.GetStyleName($layout) } catch {}
        } catch [System.Runtime.InteropServices.COMException] {
            $rec.hresult = "0x" + $_.Exception.HResult.ToString("X8")
            $rec.error = $_.Exception.Message
        } catch [System.Reflection.TargetInvocationException] {
            $rec.hresult = if ($_.Exception.InnerException) { "0x" + $_.Exception.InnerException.HResult.ToString("X8") } else { $null }
            $rec.error = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
        } catch {
            $rec.error = $_.Exception.GetType().Name + ": " + $_.Exception.Message
        }
        $result.region_attempts += $rec
        # Reset between attempts
        try { $tcPp.RemoveStyles($layout) } catch {}
    }
} catch {
    Add-ErrorRow -Result $result -Where "main" -Err $_
} finally {
    if ($pres) { try { $pres.Close() } catch {} }
    if ($tcPp) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcPp) | Out-Null } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
}

$result.verdict.style_files_count = $result.style_files_found.Count
$result.verdict.attempts_succeeded = ($result.region_attempts | Where-Object { $_.success }).Count
$result.verdict.attempts_failed = ($result.region_attempts | Where-Object { -not $_.success }).Count
$result.verdict.zero_area_succeeded = (($result.region_attempts | Where-Object { $_.tag -eq "zero_area" -and $_.success })).Count -gt 0
$result.verdict.offscreen_succeeded = (($result.region_attempts | Where-Object { $_.tag -eq "way_offscreen" -and $_.success })).Count -gt 0

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
