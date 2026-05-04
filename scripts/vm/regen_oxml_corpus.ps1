#requires -Version 5.1
<#
regen_oxml_corpus.ps1 — Excel-COM-emitted reference corpus for cross-producer
xlsx diffing.

Mirrors scripts/regen_oxml_corpus.py (which emits the openpyxl side). For each
of the same logical samples we recreate the content via Excel.Application +
Workbook.Names.Add and save as .xlsx with xlOpenXMLWorkbook (51).

Diffing openpyxl output vs Excel-Win output (via scripts/diff_oxml.py) tells
us exactly which serialization choices openpyxl makes that diverge from
Excel-native output. The diverging attributes / element orderings are the
candidate root causes for the open-repair-close behavior.

Sample matrix (matches the Python side):
  excelwin_minimal.xlsx              workbook with one sheet "Data" + cells
  excelwin_one_definedname.xlsx      + one global defined name "Total"
  excelwin_localsheet_dn.xlsx        + one local-to-sheet-0 defined name
  excelwin_hidden_dn.xlsx            + one defined name with Visible=$false
  excelwin_multi_dn.xlsx             + 5 defined names (case-insensitive ordering)

Pre-conditions:
  - Excel 2016+ installed and licensed.
  - No EXCEL.EXE running.

Usage (on VM):
  pwsh -File scripts\vm\regen_oxml_corpus.ps1 -OutDir C:\share\oxml_reference

After running, ferry to Mac:
  scp Windows-VM:'C:\share\oxml_reference\excelwin_*.xlsx' state/oxml_reference/

Then diff:
  python3 scripts/diff_oxml.py \
      state/oxml_reference/openpyxl_one_definedname.xlsx \
      state/oxml_reference/excelwin_one_definedname.xlsx \
      --only xl/workbook.xml
#>

param(
    [string]$OutDir = "$env:USERPROFILE\oxml_reference"
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

function Log($m, $c="Cyan") { Write-Host "[regen-corpus] $m" -ForegroundColor $c }

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

# xlOpenXMLWorkbook = 51 (xlsx, no macros)
$xlOpenXMLWorkbook = 51

function Initialize-MinimalWorkbook {
    param($Excel)
    $wb = $Excel.Workbooks.Add()
    $ws = $wb.Sheets.Item(1)
    $ws.Name = 'Data'
    $ws.Range('A1').Value = 'Apples'
    $ws.Range('B1').Value = 42
    $ws.Range('A2').Value = 'Pears'
    $ws.Range('B2').Value = 7
    return $wb
}

function Save-And-Close {
    param($Workbook, [string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
    }
    $Workbook.SaveAs($Path, $xlOpenXMLWorkbook)
    $Workbook.Close($false)
}

$excel = $null
$results = @()
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible       = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false

    # 1. minimal — no defined names
    Log "minimal"
    $wb = Initialize-MinimalWorkbook $excel
    $p = Join-Path $OutDir 'excelwin_minimal.xlsx'
    Save-And-Close $wb $p
    $results += [pscustomobject]@{ tag='minimal'; path=$p; bytes=(Get-Item $p).Length }

    # 2. one_definedname — one global name
    Log "one_definedname"
    $wb = Initialize-MinimalWorkbook $excel
    $wb.Names.Add('Total', "='Data'!`$B`$1:`$B`$2")
    $p = Join-Path $OutDir 'excelwin_one_definedname.xlsx'
    Save-And-Close $wb $p
    $results += [pscustomobject]@{ tag='one_definedname'; path=$p; bytes=(Get-Item $p).Length }

    # 3. localsheet_dn — local-to-sheet-0 name (worksheet-scoped Name)
    Log "localsheet_dn"
    $wb = Initialize-MinimalWorkbook $excel
    $ws = $wb.Sheets.Item(1)
    # Worksheet.Names.Add scopes the name to that worksheet (localSheetId)
    $ws.Names.Add('LocalTotal', "='Data'!`$B`$1:`$B`$2")
    $p = Join-Path $OutDir 'excelwin_localsheet_dn.xlsx'
    Save-And-Close $wb $p
    $results += [pscustomobject]@{ tag='localsheet_dn'; path=$p; bytes=(Get-Item $p).Length }

    # 4. hidden_dn — invisible name
    Log "hidden_dn"
    $wb = Initialize-MinimalWorkbook $excel
    $n = $wb.Names.Add('HiddenTotal', "='Data'!`$B`$1:`$B`$2")
    $n.Visible = $false
    $p = Join-Path $OutDir 'excelwin_hidden_dn.xlsx'
    Save-And-Close $wb $p
    $results += [pscustomobject]@{ tag='hidden_dn'; path=$p; bytes=(Get-Item $p).Length }

    # 5. multi_dn — 5 names exercising case-insensitive ordering
    Log "multi_dn"
    $wb = Initialize-MinimalWorkbook $excel
    # Insertion order intentionally NOT alphabetical so we can see whether
    # Excel sorts them on save.
    $wb.Names.Add('zeta_total',  "='Data'!`$B`$1")
    $wb.Names.Add('Alpha_Total', "='Data'!`$B`$2")
    $wb.Names.Add('delta_Total', "='Data'!`$A`$1:`$B`$2")
    $wb.Names.Add('BETA_total',  "='Data'!`$A`$1")
    $wb.Names.Add('gamma_total', "='Data'!`$A`$2")
    $p = Join-Path $OutDir 'excelwin_multi_dn.xlsx'
    Save-And-Close $wb $p
    $results += [pscustomobject]@{ tag='multi_dn'; path=$p; bytes=(Get-Item $p).Length }
}
finally {
    if ($excel) {
        try { $excel.Quit() } catch {}
        try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}

# Summary table
Log "produced corpus:"
$results | Format-Table -AutoSize | Out-String | Write-Host

# Manifest JSON for ferry tooling
$manifest = @{
    generated_at = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK')
    out_dir      = $OutDir
    samples      = $results
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutDir 'manifest.json') -Encoding UTF8
Log "manifest: $(Join-Path $OutDir 'manifest.json')"
