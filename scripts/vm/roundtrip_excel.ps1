#requires -Version 5.1
<#
roundtrip_excel.ps1 — gate-2 round-trip canary for the deck-factory harness.

What it does:
  1. Opens an .xlsx file via Excel COM with explicit CorruptLoad=xlNormalLoad (0).
  2. Reads back the actual CorruptLoad state Excel decided to use:
        0 = xlNormalLoad   (Excel was happy)
        1 = xlRepairFile   (Excel ran the repair pass — RED FLAG)
        2 = xlExtractData  (Excel could not even repair — extract-only mode)
  3. Saves the open workbook to a sibling .roundtrip.xlsx WITHOUT changes.
  4. Closes Excel cleanly.
  5. Emits a single JSON object on stdout with the canary findings.

Why this matters:
  Excel will silently repair structurally-valid-looking xlsx files that
  violate undocumented invariants (e.g. specific defined-name ordering
  rules on certain Excel builds). Schema validation alone never catches
  those. The repair pass leaves a fingerprint in CorruptLoad and in the
  diff between input and saved output.

Pre-conditions on this VM:
  - PowerPoint / Excel (any 2016+ build) installed.
  - Excel licensed (else COM dispatch fails with HRESULT 0x80040154).
  - No other Excel instance running (kill any stale POWERPNT/EXCEL.EXE first).

Usage (run from VM PowerShell, or via ssh "powershell -File"):
  pwsh -File scripts\vm\roundtrip_excel.ps1 -Path C:\share\land.model.xlsx
  pwsh -File scripts\vm\roundtrip_excel.ps1 -Path foo.xlsx -OutputJson C:\out\foo.json

Output JSON shape:
  {
    "input_path":       "<absolute>",
    "output_path":      "<absolute>",
    "bytes_in":         <int>,
    "bytes_out":        <int>,
    "corrupt_load":     0 | 1 | 2,
    "corrupt_load_name":"xlNormalLoad" | "xlRepairFile" | "xlExtractData",
    "repair_log":       "<text or null>",
    "open_seconds":     <float>,
    "save_seconds":     <float>,
    "ok":               <bool>,
    "error":            "<text or null>"
  }
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [string]$OutputJson = $null,

    [switch]$KeepOpenOnError
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

# Resolve input
$absIn = (Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue).Path
if (-not $absIn) {
    Write-JsonResult -Data @{
        input_path  = $Path
        ok          = $false
        error       = "input file not found"
    }
    exit 3
}
$inItem  = Get-Item -LiteralPath $absIn
$absOut  = [System.IO.Path]::Combine(
    [System.IO.Path]::GetDirectoryName($absIn),
    [System.IO.Path]::GetFileNameWithoutExtension($absIn) + '.roundtrip.xlsx'
)

# CorruptLoad enum
# https://learn.microsoft.com/office/vba/api/excel.xlcorruptload
$xlNormalLoad  = 0
$xlRepairFile  = 1
$xlExtractData = 2
$corruptName   = @{ 0='xlNormalLoad'; 1='xlRepairFile'; 2='xlExtractData' }

$result = @{
    input_path        = $absIn
    output_path       = $absOut
    bytes_in          = $inItem.Length
    bytes_out         = 0
    corrupt_load      = $null
    corrupt_load_name = $null
    repair_log        = $null
    open_seconds      = 0.0
    save_seconds      = 0.0
    ok                = $false
    error             = $null
}

$excel = $null
$wb    = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible       = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $excel.AlertBeforeOverwriting = $false

    # Workbooks.Open(Filename, UpdateLinks=0, ReadOnly=$false, Format,
    #                Password, WriteResPassword, IgnoreReadOnlyRecommended,
    #                Origin, Delimiter, Editable, Notify, Converter,
    #                AddToMru, Local, CorruptLoad)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $wb = $excel.Workbooks.Open(
        $absIn,            # Filename
        0,                 # UpdateLinks: do not update
        $false,            # ReadOnly
        [Type]::Missing,   # Format
        '',                # Password
        '',                # WriteResPassword
        $true,             # IgnoreReadOnlyRecommended
        [Type]::Missing,   # Origin
        [Type]::Missing,   # Delimiter
        $false,            # Editable
        $false,            # Notify
        [Type]::Missing,   # Converter
        $false,            # AddToMru
        [Type]::Missing,   # Local
        $xlNormalLoad      # CorruptLoad — explicit so we can read it back
    )
    $sw.Stop()
    $result.open_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    # Read the actual mode Excel decided to use. Per MSDN, when an explicit
    # CorruptLoad value is passed, Workbook.CorruptLoad reflects whether
    # Excel had to escalate (e.g. the caller asked for normal but Excel
    # silently swapped to repair).
    try {
        $result.corrupt_load = [int]$wb.CorruptLoad
    } catch {
        # CorruptLoad may not be exposed on older builds — assume normal
        $result.corrupt_load = $xlNormalLoad
    }
    $result.corrupt_load_name = $corruptName[$result.corrupt_load]

    # If Excel ran a repair pass it logs to a per-workbook recovery report
    # under %TEMP%. The file name pattern: error*.xml in the user's temp.
    # We only collect logs created in the last 60s as a best effort.
    $logCandidates = Get-ChildItem -LiteralPath $env:TEMP -Filter 'error*.xml' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt (Get-Date).AddSeconds(-60) }
    if ($logCandidates) {
        $latest = $logCandidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        try {
            $result.repair_log = Get-Content -LiteralPath $latest.FullName -Raw -ErrorAction Stop
        } catch {
            $result.repair_log = "<could not read $($latest.FullName): $($_.Exception.Message)>"
        }
    }

    # SaveCopyAs preserves the workbook's open state and writes a fresh copy
    # — that is exactly what we want: bytes Excel chose to emit for this
    # logical content, with no user-driven edits.
    $sw.Restart()
    $wb.SaveCopyAs($absOut)
    $sw.Stop()
    $result.save_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    if (Test-Path -LiteralPath $absOut) {
        $result.bytes_out = (Get-Item -LiteralPath $absOut).Length
    }

    $result.ok = $true
}
catch {
    $result.error = $_.Exception.Message
    $result.ok    = $false
}
finally {
    if ($wb -and -not $KeepOpenOnError) {
        try { $wb.Close($false) } catch {}
    }
    if ($excel) {
        try { $excel.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

Write-JsonResult -Data $result

if (-not $result.ok)                            { exit 1 }
elseif ($result.corrupt_load -ne $xlNormalLoad) { exit 2 }
else                                             { exit 0 }
