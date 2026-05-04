<#
Advanced runtime PowerShell probe — opens PowerPoint with a think-cell deck.

LANES (highest yield):

- Presentation.CustomXMLParts walk → THIS IS THE CHART SERIALIZATION FORMAT.
  Every think-cell chart's data lives in a custom XML part. We dump them all.
- POWERPNT.EXE module enumeration (DLLs loaded alongside tcaddin)
- POWERPNT.EXE network connections (live TCP — what is it talking to)
- CommandBars walk (every think-cell ribbon entry programmatically)
- DocumentInformation / CustomDocumentProperties / Tags
- Embedded OLE objects (the chart Excel data)

Read-only: opens deck read-only, no modifications, no saves.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [string] $DeckPath,
    [string] $XmlDumpDir
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-advanced-runtime-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        deck_path = $null
        powerpnt = [ordered]@{}
        custom_xml_parts = @()
        command_bars = @()
        recent_files_app = @()
        embedded_ole = @()
        document_props = [ordered]@{}
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

if (-not $DeckPath) {
    $candidates = @(
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed.pptx",
        "\\Mac\Home\code\apps\sales-ops-copilot\assets\LAND_thinkcell_seed_charts.pptx"
    )
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { $DeckPath = $c; break } }
}
if (-not $DeckPath -or -not (Test-Path -LiteralPath $DeckPath)) {
    Add-ErrorRow -Result $result -Where "deck" -Err "no deck found"
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}
$result.deck_path = $DeckPath

if (-not $XmlDumpDir -and $OutputPath) {
    $XmlDumpDir = Join-Path ([System.IO.Path]::GetDirectoryName($OutputPath)) "custom_xml_dumps"
}
if ($XmlDumpDir) { New-Item -ItemType Directory -Path $XmlDumpDir -Force | Out-Null }

# Copy to local temp (don't lock the original)
$tempDir = Join-Path $env:TEMP "tcw_runtime_$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$copy = Join-Path $tempDir (Split-Path -Leaf $DeckPath)
Copy-Item -LiteralPath $DeckPath -Destination $copy -Force

$ppt = $null; $pres = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application

    # Module enumeration of POWERPNT.EXE process
    try {
        $pptProc = Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($pptProc) {
            $result.powerpnt.pid = $pptProc.Id
            $result.powerpnt.module_count = $pptProc.Modules.Count
            $result.powerpnt.tc_modules = @($pptProc.Modules | Where-Object {
                $_.ModuleName -match "(?i)tc|think" -or $_.FileName -match "(?i)think.cell"
            } | ForEach-Object {
                [ordered]@{
                    name = $_.ModuleName; file = $_.FileName
                    base_address = "0x" + $_.BaseAddress.ToInt64().ToString("X16")
                    module_size = $_.ModuleMemorySize
                    file_version = (Get-Item -LiteralPath $_.FileName -ErrorAction SilentlyContinue).VersionInfo.FileVersion
                }
            })
            # Suspicious: webview2, msedgewebview2, ai-related modules
            $result.powerpnt.webview_modules = @($pptProc.Modules | Where-Object {
                $_.ModuleName -match "(?i)webview|edge|chromium|cef|electron"
            } | ForEach-Object { [ordered]@{ name = $_.ModuleName; file = $_.FileName } })
        }
    } catch { Add-ErrorRow -Result $result -Where "module_enum" -Err $_ }

    # POWERPNT TCP connections snapshot
    try {
        if ($pptProc) {
            $result.powerpnt.tcp_connections = @(Get-NetTCPConnection -OwningProcess $pptProc.Id -ErrorAction SilentlyContinue |
                Where-Object { $_.State -in @("Established", "Listen", "TimeWait") } |
                ForEach-Object {
                    [ordered]@{
                        state = [string]$_.State
                        local = "$($_.LocalAddress):$($_.LocalPort)"
                        remote = "$($_.RemoteAddress):$($_.RemotePort)"
                    }
                })
        }
    } catch { Add-ErrorRow -Result $result -Where "tcp_conn" -Err $_ }

    # Open deck read-only
    $pres = $ppt.Presentations.Open($copy, $true, $true, $false)

    # Document-level properties
    try {
        $result.document_props.name = $pres.Name
        $result.document_props.full_name = $pres.FullName
        $result.document_props.has_revisions = [bool]$pres.HasRevisionInfo
    } catch {}

    # 🎯 CustomXMLParts walk — the chart serialization
    try {
        $cxpCount = $pres.CustomXMLParts.Count
        $result.powerpnt.custom_xml_parts_count = $cxpCount
        for ($i = 1; $i -le $cxpCount; $i++) {
            try {
                $cxp = $pres.CustomXMLParts.Item($i)
                $entry = [ordered]@{
                    index = $i
                    namespace = $cxp.NamespaceURI
                    is_builtin = [bool]$cxp.BuiltIn
                }
                try { $entry.schema_count = $cxp.SchemaCollection.Count } catch {}
                $xml = [string]$cxp.XML
                $entry.xml_size = $xml.Length
                $entry.xml_sha256 = [System.BitConverter]::ToString(
                    (New-Object System.Security.Cryptography.SHA256Managed).ComputeHash(
                        [System.Text.Encoding]::UTF8.GetBytes($xml)
                    )
                ).Replace("-", "").ToLowerInvariant()
                $entry.preview = if ($xml.Length -gt 1500) { $xml.Substring(0, 1500) + "..." } else { $xml }
                $entry.is_thinkcell = ($cxp.NamespaceURI -match "think.cell")
                if ($XmlDumpDir) {
                    $safeNS = ($cxp.NamespaceURI -replace "[^A-Za-z0-9_.-]", "_")
                    if (-not $safeNS) { $safeNS = "noNS" }
                    $dumpPath = Join-Path $XmlDumpDir "part_${i}_${safeNS}.xml"
                    Set-Content -LiteralPath $dumpPath -Value $xml -Encoding UTF8
                    $entry.dumped_to = $dumpPath
                }
                $result.custom_xml_parts += $entry
            } catch { Add-ErrorRow -Result $result -Where "cxp:$i" -Err $_ }
        }
    } catch { Add-ErrorRow -Result $result -Where "cxp_enum" -Err $_ }

    # CommandBars walk for think-cell entries
    try {
        $maxBars = [Math]::Min(80, $ppt.CommandBars.Count)
        for ($b = 1; $b -le $maxBars; $b++) {
            try {
                $bar = $ppt.CommandBars.Item($b)
                $maxCtrls = [Math]::Min(150, $bar.Controls.Count)
                for ($c = 1; $c -le $maxCtrls; $c++) {
                    try {
                        $ctl = $bar.Controls.Item($c)
                        $caption = [string]$ctl.Caption
                        $tag = [string]$ctl.Tag
                        $onAction = $null; try { $onAction = [string]$ctl.OnAction } catch {}
                        if ($caption -match "(?i)think|tc[._-]|chart" -or $tag -match "(?i)tc|think" -or $onAction -match "(?i)tc|think") {
                            $result.command_bars += [ordered]@{
                                bar_name = $bar.Name
                                bar_index = $b
                                control_index = $c
                                caption = $caption
                                tag = $tag
                                on_action = $onAction
                                control_type = [int]$ctl.Type
                            }
                        }
                    } catch {}
                }
            } catch {}
        }
    } catch { Add-ErrorRow -Result $result -Where "commandbars" -Err $_ }

    # Recently-modified files in known think-cell paths during this session
    try {
        $recentRoots = @(
            "$env:LOCALAPPDATA\think-cell",
            "$env:APPDATA\think-cell",
            "$env:TEMP"
        )
        foreach ($r in $recentRoots) {
            if (-not (Test-Path -LiteralPath $r)) { continue }
            $cutoff = (Get-Date).AddMinutes(-15)
            Get-ChildItem -LiteralPath $r -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -gt $cutoff -and ($_.Name -match "(?i)tc|think" -or $_.DirectoryName -match "(?i)think.cell") } |
                Select-Object -First 20 |
                ForEach-Object {
                    $result.recent_files_app += [ordered]@{
                        path = $_.FullName; size = $_.Length
                        last_write = $_.LastWriteTime.ToString("o")
                    }
                }
        }
    } catch { Add-ErrorRow -Result $result -Where "recent_files" -Err $_ }

    # Embedded OLE objects (chart Excel data)
    try {
        foreach ($slide in $pres.Slides) {
            foreach ($shape in $slide.Shapes) {
                if ($shape.Type -in @(7, 19) -or $shape.HasChart) {  # msoEmbeddedOLE = 7, msoLinkedOLE = 19
                    $progId = $null
                    try { $progId = [string]$shape.OLEFormat.ProgID } catch {}
                    $result.embedded_ole += [ordered]@{
                        slide = $slide.SlideIndex; shape_id = $shape.Id
                        shape_name = $shape.Name; type = [int]$shape.Type
                        ole_progid = $progId
                        has_chart = [bool]$shape.HasChart
                    }
                }
            }
        }
    } catch { Add-ErrorRow -Result $result -Where "ole" -Err $_ }

} catch {
    Add-ErrorRow -Result $result -Where "main" -Err $_
} finally {
    if ($pres) { try { $pres.Close() } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
    try { Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue } catch {}
}

$result.verdict.cxp_count = $result.custom_xml_parts.Count
$result.verdict.thinkcell_cxp_count = ($result.custom_xml_parts | Where-Object { $_.is_thinkcell }).Count
$result.verdict.total_cxp_xml_size = ($result.custom_xml_parts | Measure-Object -Property xml_size -Sum).Sum
$result.verdict.tc_module_count = if ($result.powerpnt.tc_modules) { $result.powerpnt.tc_modules.Count } else { 0 }
$result.verdict.commandbar_entries = $result.command_bars.Count
$result.verdict.embedded_ole_count = $result.embedded_ole.Count
$result.verdict.tcp_connection_count = if ($result.powerpnt.tcp_connections) { $result.powerpnt.tcp_connections.Count } else { 0 }

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
