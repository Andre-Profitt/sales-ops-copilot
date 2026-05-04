#requires -Version 5.1
<#
roundtrip_powerpoint.ps1 - gate-2 partner canary for .pptx (PowerPoint COM oracle).

Mirrors roundtrip_excel.ps1 but for PresentationML. Catches the class of
hidden-corruption bugs that strict XML validation cannot see: cases where
PowerPoint silently rebuilds the file on open (slide-master inheritance
inconsistencies, broken oleObject relationships, theme part orphans, etc.).

What it does:
  1. Opens an .pptx via PowerPoint.Application.Presentations.Open with
     OpenRepair = msoFalse (do NOT auto-repair, force a clean read).
  2. If PowerPoint reports a recovery / repair condition, log it.
  3. SaveCopyAs to a sibling .roundtrip.pptx in 24 = ppSaveAsOpenXMLPresentation.
  4. Closes Presentation + quits app.
  5. Emits a single JSON object on stdout.

Why no msoTriState OpenRepair flag like Excel?
  PowerPoint's Presentations.Open does not expose a CorruptLoad enum. It
  has WithWindow / Untitled / OpenAndRepair flags. We pass OpenAndRepair
  = msoFalse. If the file is silently repaired anyway, PowerPoint logs to
  the user's TempDir (error*.xml). We sweep recent logs the same way the
  Excel canary does.

Pre-conditions on this VM:
  - Microsoft PowerPoint 2016+ installed and licensed.
  - No POWERPNT.EXE running (kill stale instances first).
  - Set up by a non-Session-0 user (PowerPoint is unreliable in Session 0).

Usage (run from VM PowerShell or via ssh "powershell -File"):
  pwsh -File scripts\vm\roundtrip_powerpoint.ps1 -Path C:\share\seed.pptx
  pwsh -File scripts\vm\roundtrip_powerpoint.ps1 -Path foo.pptx -OutputJson C:\out\foo.json

Output JSON shape:
  {
    "input_path":     "<absolute>",
    "output_path":    "<absolute>",
    "bytes_in":       <int>,
    "bytes_out":      <int>,
    "slide_count":    <int>,
    "had_repair_log": <bool>,
    "repair_log":     "<text or null>",
    "open_seconds":   <float>,
    "save_seconds":   <float>,
    "ok":             <bool>,
    "error":          "<text or null>"
  }

Exit codes:
    0   clean (no repair log surfaced)
    1   COM/IO failure (script could not run)
    2   PowerPoint emitted a repair log alongside the open
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [string]$OutputJson = $null
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

function Write-JsonResult {
    param([hashtable]$Data)
    $json = $Data | ConvertTo-Json -Depth 6 -Compress:$false
    if ($OutputJson) {
        Set-Content -LiteralPath $OutputJson -Value $json -Encoding UTF8
    }
    Write-Host '---ROUNDTRIP_JSON_BEGIN---'
    Write-Host $json
    Write-Host '---ROUNDTRIP_JSON_END---'
}

$absIn = (Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue).Path
if (-not $absIn) {
    Write-JsonResult -Data @{ input_path = $Path; ok = $false; error = "input file not found" }
    exit 1
}
$inItem  = Get-Item -LiteralPath $absIn
$absOut  = [System.IO.Path]::Combine(
    [System.IO.Path]::GetDirectoryName($absIn),
    [System.IO.Path]::GetFileNameWithoutExtension($absIn) + '.roundtrip.pptx'
)

# Office MsoTriState
$msoFalse = 0
$msoTrue  = -1
# PpSaveAsFileType
$ppSaveAsOpenXMLPresentation = 24

$result = @{
    input_path     = $absIn
    output_path    = $absOut
    bytes_in       = $inItem.Length
    bytes_out      = 0
    slide_count    = 0
    had_repair_log = $false
    repair_log     = $null
    open_seconds   = 0.0
    save_seconds   = 0.0
    ok             = $false
    error          = $null
}

$ppt = $null
$pres = $null
$tempBefore = (Get-Date)

try {
    # Snapshot of pre-existing log files so we don't false-positive on
    # logs older than this run.
    $preLogs = Get-ChildItem -LiteralPath $env:TEMP -Filter 'error*.xml' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName

    $ppt = New-Object -ComObject PowerPoint.Application
    # PowerPoint cannot run fully invisible on most builds; minimize instead.
    try { $ppt.WindowState = 2 } catch {}  # ppWindowMinimized = 2

    # Presentations.Open(FileName, ReadOnly, Untitled, WithWindow)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $pres = $ppt.Presentations.Open(
        $absIn,
        $msoFalse,  # ReadOnly
        $msoFalse,  # Untitled
        $msoFalse   # WithWindow
    )
    $sw.Stop()
    $result.open_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)
    $result.slide_count = $pres.Slides.Count

    # SaveCopyAs is the safe path - no overwrite of the input.
    $sw.Restart()
    $pres.SaveCopyAs($absOut, $ppSaveAsOpenXMLPresentation)
    $sw.Stop()
    $result.save_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    if (Test-Path -LiteralPath $absOut) {
        $result.bytes_out = (Get-Item -LiteralPath $absOut).Length
    }

    # Sweep for new error*.xml logs created during this run.
    $postLogs = Get-ChildItem -LiteralPath $env:TEMP -Filter 'error*.xml' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $tempBefore }
    foreach ($lg in $postLogs) {
        if ($preLogs -notcontains $lg.FullName) {
            try {
                $result.repair_log    = (Get-Content -LiteralPath $lg.FullName -Raw -ErrorAction Stop)
                $result.had_repair_log = $true
                break
            } catch {}
        }
    }

    $result.ok = $true
}
catch {
    $result.error = $_.Exception.Message
    $result.ok    = $false
}
finally {
    if ($pres) {
        try { $pres.Close() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pres) | Out-Null } catch {}
    }
    if ($ppt) {
        try { $ppt.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {}
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

Write-JsonResult -Data $result

if (-not $result.ok)            { exit 1 }
elseif ($result.had_repair_log) { exit 2 }
else                            { exit 0 }
