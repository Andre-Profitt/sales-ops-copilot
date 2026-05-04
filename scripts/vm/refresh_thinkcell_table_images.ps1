<#
.SYNOPSIS
Refresh Think-Cell AddRangeImage shapes in a PPTX from an Excel workbook.

.PARAMETER Pptx
Input pptx that has placeholders named per binding registry.

.PARAMETER Workbook
Connected factory workbook with the source ranges/named ranges.

.PARAMETER BindingsJson
JSON string: list of {slide_id, name, source} where `source` is e.g.
"workbook.named_ranges.S07_TopDealsLand" or "workbook.range.Sheet!A1:H11".

.PARAMETER Out
Output pptx path.
#>

param(
    [Parameter(Mandatory=$true)][string]$Pptx,
    [Parameter(Mandatory=$true)][string]$Workbook,
    [Parameter(Mandatory=$true)][string]$BindingsJson,
    [Parameter(Mandatory=$true)][string]$Out
)

$ErrorActionPreference = 'Stop'

# BindingsJson arrives as a JSON-encoded string of a JSON list
$bindings = ConvertFrom-Json (ConvertFrom-Json $BindingsJson)

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$ppt = New-Object -ComObject PowerPoint.Application

try {
    $wb = $excel.Workbooks.Open($Workbook)
    $pres = $ppt.Presentations.Open($Pptx, $true, $false, $false)  # ReadOnly=true, Untitled, WithWindow=false

    # Acquire Think-Cell update object via COM
    $tcAddin = $null
    foreach ($addin in $excel.COMAddIns) {
        if ($addin.Description -match 'think-cell') { $tcAddin = $addin; break }
    }
    if (-not $tcAddin) { throw 'think-cell COM add-in not found in Excel' }
    $tc = $tcAddin.Object

    foreach ($b in $bindings) {
        $name = $b.name
        $src  = $b.source
        # parse source: 'workbook.named_ranges.<X>' or 'workbook.range.<Sheet!A1:H11>'
        if ($src -like 'workbook.named_ranges.*') {
            $rangeRef = $src.Substring('workbook.named_ranges.'.Length)
            $rng = $wb.Names.Item($rangeRef).RefersToRange
        } elseif ($src -like 'workbook.range.*') {
            $rangeRef = $src.Substring('workbook.range.'.Length)
            $rng = $wb.Application.Range($rangeRef)
        } else {
            Write-Warning "skipping binding $name: unsupported source '$src'"
            continue
        }
        $tc.UpdateBatch.AddRangeImage($pres, $name, $rng) | Out-Null
        Write-Host "queued AddRangeImage for $name"
    }
    $tc.UpdateBatch.Send() | Out-Null

    $pres.SaveAs($Out)
    $pres.Close()
    $wb.Close($false)
}
finally {
    $ppt.Quit()
    $excel.Quit()
}
