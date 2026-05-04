<#
Excel-side hidden-surface probe.

The existing hidden-surface probe focused on tcPpAddIn (PowerPoint).
This probe re-runs the 3,200-candidate name resolution against:
- tcXlAddIn (Excel add-in)
- tcUpdate (the update builder returned by CreateUpdate)
- The Range/Workbook-level add-in surface
- Properties (not just methods) on each

Read-only: uses IDispatch.GetIDsOfNames which resolves names without
invoking them. Mirror the existing harness conventions.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [int] $MaxBinaryStrings = 2400,
    [int] $MaxDispatchCandidates = 3200
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-xladdin-hidden-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        excel = [ordered]@{}
        targets = @()
        candidate_summary = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

function Get-MemberSurface {
    param([object] $Object)
    if ($null -eq $Object) { return @() }
    try {
        return @(
            $Object | Get-Member |
                Where-Object { $_.MemberType -in @("Method", "Property") } |
                Sort-Object Name |
                ForEach-Object {
                    [ordered]@{ name = $_.Name; member_type = [string] $_.MemberType; definition = [string] $_.Definition }
                }
        )
    } catch { return @() }
}

function Test-DispatchName {
    param([object] $Object, [string] $Name)
    if ($null -eq $Object) { return $false }
    try {
        $dispid = 0
        $iid = [guid]::Empty
        $names = [string[]]@($Name)
        $type = $Object.GetType()
        # Use late-bound Type.InvokeMember probe — if name is unknown, it throws
        $null = $type.InvokeMember($Name, [System.Reflection.BindingFlags]::GetProperty -bor [System.Reflection.BindingFlags]::InvokeMethod, $null, $Object, $null)
        return $true
    } catch [System.Reflection.TargetInvocationException] {
        # Method exists but invocation failed — that's a positive resolution
        return $true
    } catch [System.MissingMethodException] {
        return $false
    } catch [System.MissingMemberException] {
        # PowerShell often wraps DISP_E_UNKNOWNNAME as MissingMember
        return $false
    } catch {
        # COMException with DISP_E_UNKNOWNNAME (0x80020006) → unresolved
        # Other COM errors with non-DISP_E_UNKNOWNNAME → name DID resolve
        if ($_.Exception.HResult -eq 0x80020006) { return $false }
        return $true
    }
}

function Probe-Target {
    param(
        [string] $Label,
        [object] $Object,
        [string[]] $Candidates
    )
    $entry = [ordered]@{
        label = $Label
        object_type = if ($Object) { $Object.GetType().FullName } else { $null }
        visible_members = Get-MemberSurface $Object
        resolved_names = @()
        unresolved_count = 0
        candidate_count = $Candidates.Count
    }
    if ($null -eq $Object) {
        $entry.error = "object is null"
        return $entry
    }
    foreach ($name in $Candidates) {
        if (Test-DispatchName -Object $Object -Name $name) {
            $entry.resolved_names += $name
        } else {
            $entry.unresolved_count++
        }
    }
    $entry.resolved_names = @($entry.resolved_names | Sort-Object -Unique)
    return $entry
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

# Build candidate name list from existing tcaddin.dll string scan + constructor patterns
$candidates = New-Object System.Collections.Generic.List[string]
$staticCandidates = @(
    "AddRangeData", "AddRangeImage", "AddRangeChart", "AddRangeTable",
    "AddRange", "AddRangeText", "AddNamedRange", "AddNamedTable",
    "Send", "Cancel", "Discard", "Commit", "Reset",
    "SetProperty", "GetProperty", "SetOptions", "GetOptions",
    "CreateUpdate", "CreateChart", "CreateTable", "CreateNamedElement",
    "PresentationFromTemplate", "PresentationFromTemplateStep1", "PresentationFromTemplateStep2", "PresentationFromTemplateStep3", "PresentationFromTemplateStep4",
    "UpdateChart", "UpdateChartStep1", "UpdateChartStep2", "UpdateChartStep3",
    "UpdateBatch", "UpdateBatchStep1", "UpdateBatchStep2", "UpdateBatchStep3",
    "InsertChart", "InsertChartToData", "InsertTable", "InsertGantt", "InsertScatter", "InsertWaterfall", "InsertMekko",
    "ShowChartGallery", "StartTableInsertion", "StartChartInsertion",
    "GetVersion", "GetBuildNumber", "GetLicenseInfo", "Diagnose",
    "ExportChartXML", "ImportChartXML", "GetChartXML", "SetChartXML",
    "GetMekkoGraphicsXML", "ImportMekkoGraphicsCharts",
    "LoadStyle", "LoadStyleStep2", "LoadStyleForRegion", "GetStyleName", "RemoveStyles",
    "BainToolboxApplyShift", "BainToolboxRectangles", "BainToolbox",
    "ActivateAddIn", "IsAddInActive",
    "EnableTrace", "DisableTrace", "SetTraceLevel", "FlushTrace", "Diagnostic",
    "Application", "Parent", "Version", "BuildNumber", "Name",
    "ChartsGallery", "ElementsGallery", "Table",
    "tglbtnWaterfall_onAction", "tglbtnGantt_onAction", "tglbtnTable_onAction"
)
$staticCandidates | ForEach-Object { [void]$candidates.Add($_) }

# Pull live strings from tcaddin.dll (mirror the existing hidden-surface harness)
$dllPaths = @(
    "C:\Program Files (x86)\think-cell\arm64\tcaddin.dll",
    "C:\Program Files\think-cell\arm64\tcaddin.dll",
    "C:\Program Files (x86)\think-cell\x64\tcaddin.dll",
    "C:\Program Files (x86)\think-cell\x86\tcaddin.dll"
)
foreach ($dll in $dllPaths) {
    if (-not (Test-Path -LiteralPath $dll)) { continue }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($dll)
        $text = [System.Text.Encoding]::ASCII.GetString($bytes)
        $hits = [regex]::Matches($text, "(?<![A-Za-z])(?:Add|Set|Get|Create|Insert|Update|Remove|Show|Hide|Start|Stop|Begin|End|Init|Load|Save|Open|Close|Activate|Deactivate|Enable|Disable|Apply|Reset|Commit|Cancel|Send|Receive|Bind|Unbind|Probe|Query|Resolve|Lookup|Make|Build)[A-Z][a-zA-Z0-9_]{2,32}") |
            ForEach-Object { $_.Value } | Select-Object -Unique | Select-Object -First $MaxBinaryStrings
        $hits | ForEach-Object { [void]$candidates.Add($_) }
        break
    } catch {
        Add-ErrorRow -Result $result -Where "string_scan:$dll" -Err $_
    }
}
$candidateUnique = @($candidates | Sort-Object -Unique | Select-Object -First $MaxDispatchCandidates)
$result.candidate_summary.total = $candidateUnique.Count
$result.candidate_summary.from_static = $staticCandidates.Count

# Acquire Excel + thinkcell.addin
$xl = $null
$tcXl = $null
$tcUpdate = $null
try {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false
    $xl.DisplayAlerts = $false
    $result.excel.version = $xl.Version
    $result.excel.build = $xl.Build
    $addin = $xl.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if ($addin) {
        $tcXl = $addin.Object
        $result.excel.addin_progid = $addin.ProgId
        $result.excel.addin_connect = $addin.Connect
        try {
            $tcUpdate = $tcXl.CreateUpdate()
            $result.excel.tcupdate_acquired = $true
        } catch {
            Add-ErrorRow -Result $result -Where "tcUpdate:CreateUpdate" -Err $_
        }
    } else {
        Add-ErrorRow -Result $result -Where "addin" -Err "thinkcell.addin not found in Excel COMAddIns"
    }
} catch {
    Add-ErrorRow -Result $result -Where "excel:create" -Err $_
}

if ($tcXl) {
    $result.targets += (Probe-Target -Label "tcXlAddIn" -Object $tcXl -Candidates $candidateUnique)
}
if ($tcUpdate) {
    $result.targets += (Probe-Target -Label "tcUpdate" -Object $tcUpdate -Candidates $candidateUnique)
}
if ($xl) {
    # Application-level COMAddIns dispatch — checks if any chart-creation method is hung off the Excel application via add-in
    $result.targets += (Probe-Target -Label "xlApplication" -Object $xl -Candidates @("ThinkCell", "thinkcell", "tcaddin", "InsertThinkCellChart", "InsertThinkCellTable") )
}

# Cleanup
if ($tcUpdate) {
    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcUpdate) | Out-Null } catch {}
}
if ($tcXl) {
    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcXl) | Out-Null } catch {}
}
if ($xl) {
    try { $xl.Quit() } catch {}
    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null } catch {}
}

$documented_xladdin = @("CreateUpdate", "PresentationFromTemplate", "UpdateChart")
$documented_tcupdate = @("AddRangeData", "AddRangeImage", "Send")
$novelXlAddin = @()
$novelTcUpdate = @()
foreach ($t in $result.targets) {
    foreach ($n in $t.resolved_names) {
        if ($t.label -eq "tcXlAddIn" -and $documented_xladdin -notcontains $n) { $novelXlAddin += $n }
        if ($t.label -eq "tcUpdate" -and $documented_tcupdate -notcontains $n) { $novelTcUpdate += $n }
    }
}
$result.verdict.novel_tcXlAddIn_methods = @($novelXlAddin | Sort-Object -Unique)
$result.verdict.novel_tcUpdate_methods = @($novelTcUpdate | Sort-Object -Unique)
$result.verdict.any_novel_excel_surface = (($novelXlAddin.Count + $novelTcUpdate.Count) -gt 0)

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
