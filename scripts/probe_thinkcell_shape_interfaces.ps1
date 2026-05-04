<#
think-cell SHAPE COM-interface enumeration probe.

Open a known think-cell deck (read-only copy), walk every Shape, attempt
QueryInterface against well-known interfaces. Look for non-standard
properties, OLE casts, and anything beyond the standard MSO.Shape.
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
        schema = "simcorp-thinkcell-shape-interfaces-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        deck_path = $null
        slide_count = 0
        shape_count = 0
        sampled_shapes = @()
        unique_iface_combos = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}
function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$cs = @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace TcShapeIfaces {
    public static class Probe {
        public static readonly string[][] Candidates = new string[][] {
            new string[] { "IDispatch", "00020400-0000-0000-C000-000000000046" },
            new string[] { "IConnectionPointContainer", "B196B284-BAB4-101A-B69C-00AA00341D07" },
            new string[] { "IProvideClassInfo", "B196B283-BAB4-101A-B69C-00AA00341D07" },
            new string[] { "IProvideClassInfo2", "A6BC3AC0-DBAA-11CE-9DE3-00AA004BB851" },
            new string[] { "IPersist", "0000010C-0000-0000-C000-000000000046" },
            new string[] { "IPersistStream", "00000109-0000-0000-C000-000000000046" },
            new string[] { "IPersistStorage", "0000010A-0000-0000-C000-000000000046" },
            new string[] { "IPersistMemory", "BD1AE5E0-A6AE-11CE-BD37-504200C10000" },
            new string[] { "IOleObject", "00000112-0000-0000-C000-000000000046" },
            new string[] { "IViewObject", "0000010D-0000-0000-C000-000000000046" },
            new string[] { "IDataObject", "0000010E-0000-0000-C000-000000000046" },
            new string[] { "IPropertyBag", "55272A00-42CB-11CE-8135-00AA004BB851" },
            new string[] { "IRunnableObject", "00000126-0000-0000-C000-000000000046" },
            new string[] { "ITypeInfo", "00020401-0000-0000-C000-000000000046" }
        };

        public static List<KeyValuePair<string, string>> Test(object o) {
            var results = new List<KeyValuePair<string,string>>();
            if (o == null) return results;
            IntPtr p = Marshal.GetIUnknownForObject(o);
            if (p == IntPtr.Zero) return results;
            try {
                foreach (var c in Candidates) {
                    Guid g = new Guid(c[1]);
                    IntPtr pi = IntPtr.Zero;
                    int hr = Marshal.QueryInterface(p, ref g, out pi);
                    if (hr == 0 && pi != IntPtr.Zero) {
                        results.Add(new KeyValuePair<string, string>(c[0], "0x" + hr.ToString("X8")));
                        Marshal.Release(pi);
                    }
                }
            } finally {
                Marshal.Release(p);
            }
            return results;
        }
    }
}
"@
try { Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop } catch {
    if ($_.Exception.Message -notmatch "already exists") {
        $errResult = New-Result
        Add-ErrorRow -Result $errResult -Where "Add-Type" -Err $_
        $errResult | ConvertTo-Json -Depth 100
        exit 1
    }
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

if (-not $DeckPath) {
    $candidates = @(
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed.pptx",
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed_charts.pptx",
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_seed_thinkcell.pptx"
    )
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { $DeckPath = $c; break } }
}
if (-not $DeckPath -or -not (Test-Path -LiteralPath $DeckPath)) {
    Add-ErrorRow -Result $result -Where "deck_resolution" -Err "no deck"
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}
$result.deck_path = $DeckPath

$tempDir = Join-Path $env:TEMP "tcw_shape_ifaces_$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$copy = Join-Path $tempDir (Split-Path -Leaf $DeckPath)
Copy-Item -LiteralPath $DeckPath -Destination $copy -Force

$ppt = $null; $pres = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open($copy, $true, $true, $false)
    $result.slide_count = $pres.Slides.Count
    $sampledIdx = 0
    foreach ($slide in $pres.Slides) {
        foreach ($shape in $slide.Shapes) {
            $result.shape_count++
            if ($sampledIdx -ge 60) { continue }
            $tagCount = 0
            try { $tagCount = $shape.Tags.Count } catch {}
            $isManaged = $false
            $managedTagValue = $null
            try {
                if ($tagCount -gt 0) {
                    for ($i = 1; $i -le $tagCount; $i++) {
                        if ($shape.Tags.Name($i) -eq "THINKCELLSHAPEDONOTDELETE") {
                            $isManaged = $true
                            $managedTagValue = $shape.Tags.Value($i)
                            break
                        }
                    }
                }
            } catch {}
            # Sample managed shapes preferentially
            if (-not $isManaged -and $sampledIdx -gt 30) { continue }

            $entry = [ordered]@{
                slide_index = $slide.SlideIndex
                shape_id = $shape.Id
                shape_name = $shape.Name
                shape_type = [int]$shape.Type
                managed = $isManaged
                managed_tag_value = $managedTagValue
            }
            try { $entry.has_chart = [bool]$shape.HasChart } catch { $entry.has_chart = $null }
            try { $entry.has_table = [bool]$shape.HasTable } catch { $entry.has_table = $null }
            try { $entry.has_text_frame = [bool]$shape.HasTextFrame } catch { $entry.has_text_frame = $null }
            try {
                $oleType = $shape.Type
                if ($oleType -eq 7 -or $oleType -eq 19) {  # msoEmbeddedOLEObject = 7, msoLinkedOLEObject = 19
                    $entry.ole_progid = [string]$shape.OLEFormat.ProgID
                }
            } catch {}
            try {
                $iface_results = [TcShapeIfaces.Probe]::Test($shape)
                $entry.supported_interfaces = @($iface_results | ForEach-Object { $_.Key } | Sort-Object -Unique)
                $key = ($entry.supported_interfaces -join ",")
                if (-not $result.unique_iface_combos.Contains($key)) {
                    $result.unique_iface_combos[$key] = 0
                }
                $result.unique_iface_combos[$key]++
            } catch {
                Add-ErrorRow -Result $result -Where "iface_test:slide=$($slide.SlideIndex):shape=$($shape.Id)" -Err $_
            }
            $result.sampled_shapes += $entry
            $sampledIdx++
        }
    }
} catch {
    Add-ErrorRow -Result $result -Where "main" -Err $_
} finally {
    if ($pres) { try { $pres.Close() } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
    try { Remove-Item -LiteralPath $tempDir -Recurse -Force } catch {}
}

$result.verdict.shape_count = $result.shape_count
$result.verdict.sampled_count = $result.sampled_shapes.Count
$result.verdict.managed_count = ($result.sampled_shapes | Where-Object { $_.managed }).Count
$result.verdict.unique_iface_combo_count = $result.unique_iface_combos.Count
$result.verdict.unique_iface_combos_summary = @($result.unique_iface_combos.GetEnumerator() | ForEach-Object { [ordered]@{ ifaces = $_.Key; count = $_.Value } })

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
