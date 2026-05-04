#requires -Version 5.1
<#
roundtrip_xlsx_openxmlsdk.ps1 - gate-2 oracle for xlsx using DocumentFormat.OpenXml SDK.

Why this exists:
  Excel COM (Workbooks.Open) fails in non-interactive Session-0 (SSH-launched
  PowerShell) with "Unable to get the Open property of the Workbooks class".
  Trusted-locations + Desktop-folder fixes do not resolve it. The OpenXml SDK
  is Microsoft's reference OOXML library - same one Excel uses internally for
  validation - and runs entirely headless without Excel.

What it does:
  1. Loads DocumentFormat.OpenXml.dll (pinned to 2.20.0, last self-contained
     release that loads into .NET Framework 4.x without dependencies).
  2. Opens the xlsx via SpreadsheetDocument.Open(path, isEditable=false).
  3. Runs OpenXmlValidator.Validate(doc) at the most recent supported
     FileFormatVersion (Office2019). Returns IEnumerable<ValidationErrorInfo>
     covering schema violations, spec violations, and cross-part inconsistencies
     - the same class of checks Excel's repair pass would catch.
  4. Walks the workbook part to confirm parseability and count defined names.
  5. Emits a JSON report with the findings.

Pre-conditions:
  - PowerShell 5.1+ (this VM has 5.1.26100).
  - DocumentFormat.OpenXml 2.20.0 installed via PackageManagement (use
    install_openxml.ps1 - reusable bootstrap).

Usage:
  pwsh -File scripts\vm\roundtrip_xlsx_openxmlsdk.ps1 -Path C:\share\foo.xlsx
  pwsh -File scripts\vm\roundtrip_xlsx_openxmlsdk.ps1 -Path foo.xlsx -OutputJson out.json

Output JSON shape (matches roundtrip_excel.ps1's contract closely):
  {
    "input_path":           "<absolute>",
    "bytes_in":             <int>,
    "bytes_out":            0,
    "validation_count":     <int>,
    "validation_errors":    [ { id, path, description, severity }, ... ],
    "defined_name_count":   <int>,
    "sheet_count":          <int>,
    "ole_object_count":     <int>,
    "open_seconds":         <float>,
    "validate_seconds":     <float>,
    "ok":                   <bool>,
    "error":                "<text or null>"
  }

Exit codes:
    0  clean (zero validation errors)
    1  load/parse failure (could not open file)
    2  validation errors present (Excel would repair-pass this file)
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [string]$OutputJson = $null,

    [string]$DllPath = "$env:LOCALAPPDATA\PackageManagement\NuGet\Packages\DocumentFormat.OpenXml.2.20.0\lib\net35\DocumentFormat.OpenXml.dll"
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

function Write-JsonResult {
    param([hashtable]$Data)
    $json = $Data | ConvertTo-Json -Depth 8 -Compress:$false
    if ($OutputJson) {
        # Write WITHOUT BOM so Mac-side json.loads consumes cleanly.
        [System.IO.File]::WriteAllText($OutputJson, $json, (New-Object System.Text.UTF8Encoding $false))
    }
    Write-Host '---ROUNDTRIP_JSON_BEGIN---'
    Write-Host $json
    Write-Host '---ROUNDTRIP_JSON_END---'
}

# Resolve input
$absIn = (Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue).Path
if (-not $absIn) {
    Write-JsonResult -Data @{ input_path = $Path; ok = $false; error = "input file not found" }
    exit 1
}

# Load OpenXml DLL
if (-not (Test-Path -LiteralPath $DllPath)) {
    Write-JsonResult -Data @{
        input_path = $absIn
        ok         = $false
        error      = "OpenXml DLL not found at $DllPath - run install_openxml.ps1 first"
    }
    exit 1
}
try {
    Add-Type -Path $DllPath -ErrorAction Stop
} catch {
    Write-JsonResult -Data @{
        input_path = $absIn
        ok         = $false
        error      = "could not Add-Type DocumentFormat.OpenXml: $($_.Exception.Message)"
    }
    exit 1
}

$inItem = Get-Item -LiteralPath $absIn
$absOut = [System.IO.Path]::Combine(
    [System.IO.Path]::GetDirectoryName($absIn),
    [System.IO.Path]::GetFileNameWithoutExtension($absIn) + '.roundtrip.xlsx'
)

$result = @{
    input_path         = $absIn
    output_path        = $absOut
    bytes_in           = $inItem.Length
    bytes_out          = 0
    validation_count   = 0
    validation_errors  = @()
    defined_name_count = 0
    sheet_count        = 0
    ole_object_count   = 0
    open_seconds       = 0.0
    validate_seconds   = 0.0
    save_seconds       = 0.0
    ok                 = $false
    error              = $null
}

$doc = $null
try {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    # Open read-only — we are not editing, only validating.
    $doc = [DocumentFormat.OpenXml.Packaging.SpreadsheetDocument]::Open($absIn, $false)
    $sw.Stop()
    $result.open_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    $wbPart = $doc.WorkbookPart
    if ($wbPart -ne $null) {
        $wb = $wbPart.Workbook
        if ($wb.Sheets -ne $null) {
            $result.sheet_count = ($wb.Sheets.ChildElements | Measure-Object).Count
        }
        # PS5.1 cannot use the .Elements[[Type]] indexer on generic methods;
        # walk children instead.
        $dnElement = $wb.ChildElements |
            Where-Object { $_ -is [DocumentFormat.OpenXml.Spreadsheet.DefinedNames] } |
            Select-Object -First 1
        if ($dnElement -ne $null) {
            $result.defined_name_count = ($dnElement.ChildElements | Measure-Object).Count
        }
        # Count oleObjects across all worksheet parts
        $oleCount = 0
        foreach ($wsp in $wbPart.WorksheetParts) {
            $oleCount += ($wsp.EmbeddedObjectParts | Measure-Object).Count
        }
        $result.ole_object_count = $oleCount
    }

    # Validate. FileFormatVersions: Office2007=1, Office2010=2, Office2013=4, Office2016=8, Office2019=16, Office2021=32.
    # Use Office2019 as the broadest stable target; newer files validate fine.
    $sw.Restart()
    $validator = New-Object DocumentFormat.OpenXml.Validation.OpenXmlValidator(
        [DocumentFormat.OpenXml.FileFormatVersions]::Office2019
    )
    $errors = $validator.Validate($doc)
    $sw.Stop()
    $result.validate_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    $errorList = @()
    foreach ($e in $errors) {
        $errorList += @{
            id           = "$($e.Id)"
            path         = if ($e.Path) { "$($e.Path.XPath)" } else { $null }
            part         = if ($e.Part) { "$($e.Part.Uri)" } else { $null }
            description  = "$($e.Description)"
            severity     = "$($e.ErrorType)"
            related_node = if ($e.RelatedNode) { "$($e.RelatedNode.LocalName)" } else { $null }
        }
    }
    $result.validation_errors = $errorList
    $result.validation_count = $errorList.Count

    # Close the read-only handle before cloning so we don't double-open.
    try { $doc.Close() } catch {}
    try { $doc.Dispose() } catch {}
    $doc = $null

    # Roundtrip-save: copy the input bytes to a sibling path, open the COPY
    # with isEditable=true, save, and close. The save flushes whatever the
    # SDK normalizes (attribute order, namespace prefixes, etc.). Diffing
    # the original vs the roundtrip surfaces what an OOXML-spec-compliant
    # serializer would silently rewrite — a strong proxy for what Excel's
    # repair pass would change.
    $sw.Restart()
    if (Test-Path -LiteralPath $absOut) { Remove-Item -LiteralPath $absOut -Force }
    Copy-Item -LiteralPath $absIn -Destination $absOut -Force
    $rtDoc = [DocumentFormat.OpenXml.Packaging.SpreadsheetDocument]::Open($absOut, $true)
    try {
        $rtDoc.Save()
    } finally {
        try { $rtDoc.Close() } catch {}
        try { $rtDoc.Dispose() } catch {}
    }
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
    if ($doc) {
        try { $doc.Close() } catch {}
        try { $doc.Dispose() } catch {}
    }
}

Write-JsonResult -Data $result

if (-not $result.ok)              { exit 1 }
elseif ($result.validation_count) { exit 2 }
else                              { exit 0 }
