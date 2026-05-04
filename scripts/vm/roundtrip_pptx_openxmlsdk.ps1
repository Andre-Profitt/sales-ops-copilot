#requires -Version 5.1
<#
roundtrip_pptx_openxmlsdk.ps1 - gate-2 oracle for pptx using DocumentFormat.OpenXml SDK.

Mirror of roundtrip_xlsx_openxmlsdk.ps1 for PresentationML. Same rationale:
PowerPoint COM (Presentations.Open) is unreliable in non-interactive
Session-0 PowerShell, while the OpenXml SDK runs entirely headless.

What it does:
  1. Loads DocumentFormat.OpenXml.dll (pinned to 2.20.0, last self-contained
     release that loads under .NET Framework 4.x without transitive deps).
  2. Opens the pptx via PresentationDocument.Open(path, isEditable=false).
  3. Walks the presentation part: counts slides, slide masters, slide layouts,
     and oleObject embeddings.
  4. Runs OpenXmlValidator.Validate(doc) at FileFormatVersions.Office2019.
  5. Roundtrip-saves a .roundtrip.pptx via Open(copy, isEditable=true) + Save +
     Dispose so gate-3 can structurally diff input vs SDK-normalized output.
  6. Emits a single JSON report on stdout.

Pre-conditions:
  - PowerShell 5.1+
  - DocumentFormat.OpenXml 2.20.0 installed via install_openxml.ps1 (idempotent).

Usage:
  pwsh -File scripts\vm\roundtrip_pptx_openxmlsdk.ps1 -Path C:\share\seed.pptx
  pwsh -File scripts\vm\roundtrip_pptx_openxmlsdk.ps1 -Path foo.pptx -OutputJson out.json

Output JSON shape:
  {
    "input_path":         "<absolute>",
    "output_path":        "<absolute>",
    "bytes_in":           <int>,
    "bytes_out":          <int>,
    "validation_count":   <int>,
    "validation_errors":  [ { id, path, part, description, severity, related_node }, ... ],
    "slide_count":        <int>,
    "master_count":       <int>,
    "layout_count":       <int>,
    "ole_object_count":   <int>,
    "open_seconds":       <float>,
    "validate_seconds":   <float>,
    "save_seconds":       <float>,
    "ok":                 <bool>,
    "error":              "<text or null>"
  }

Exit codes:
    0  clean (zero validation errors, parsed cleanly)
    1  load/parse failure
    2  validation errors present
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
    [System.IO.Path]::GetFileNameWithoutExtension($absIn) + '.roundtrip.pptx'
)

$result = @{
    input_path         = $absIn
    output_path        = $absOut
    bytes_in           = $inItem.Length
    bytes_out          = 0
    validation_count   = 0
    validation_errors  = @()
    slide_count        = 0
    master_count       = 0
    layout_count       = 0
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
    $doc = [DocumentFormat.OpenXml.Packaging.PresentationDocument]::Open($absIn, $false)
    $sw.Stop()
    $result.open_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 3)

    $presPart = $doc.PresentationPart
    if ($presPart -ne $null) {
        $result.slide_count  = ($presPart.SlideParts | Measure-Object).Count
        $result.master_count = ($presPart.SlideMasterParts | Measure-Object).Count
        # Layouts hang off masters
        $layouts = 0
        foreach ($mp in $presPart.SlideMasterParts) {
            $layouts += ($mp.SlideLayoutParts | Measure-Object).Count
        }
        $result.layout_count = $layouts
        # oleObjects on slides (the think-cell anchors)
        $ole = 0
        foreach ($sp in $presPart.SlideParts) {
            $ole += ($sp.EmbeddedObjectParts | Measure-Object).Count
        }
        $result.ole_object_count = $ole
    }

    # Validate at the broadest stable target.
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

    # Close read-only handle before cloning so we don't double-open the file.
    try { $doc.Close() } catch {}
    try { $doc.Dispose() } catch {}
    $doc = $null

    # Roundtrip save: copy + open editable + save + dispose. Diff input vs
    # output to see what the SDK normalizes (proxy for what PowerPoint's
    # repair pass would change).
    $sw.Restart()
    if (Test-Path -LiteralPath $absOut) { Remove-Item -LiteralPath $absOut -Force }
    Copy-Item -LiteralPath $absIn -Destination $absOut -Force
    $rtDoc = [DocumentFormat.OpenXml.Packaging.PresentationDocument]::Open($absOut, $true)
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
