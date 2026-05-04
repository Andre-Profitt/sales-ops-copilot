<#
Probe for undocumented think-cell automation surfaces without invoking unknown
methods. The probe:

- enumerates visible PowerPoint/Excel COM members,
- checks candidate method names through IDispatch.GetIDsOfNames,
- scans installed think-cell binaries for command-like strings,
- inventories PowerPoint command bars and add-in registry entries.

It intentionally does not call unknown methods. DISPIDs are name-resolution
evidence only; a found DISPID is not a production contract.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [int] $MaxBinaryStrings = 600,
    [int] $MaxDispatchCandidates = 1200
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-hidden-surface-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        thinkcell = [ordered]@{}
        registry = @()
        command_bars = @()
        visible_members = [ordered]@{}
        binary_string_hits = @()
        dispatch_name_probe = [ordered]@{}
        candidate_summary = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $ErrorRecord)
    $message = if ($ErrorRecord.Exception) { $ErrorRecord.Exception.Message } else { [string] $ErrorRecord }
    $Result.errors += [ordered]@{ where = $Where; message = $message }
}

function Find-PpttcExe {
    $candidates = @(
        "C:\Program Files\think-cell\ppttc.exe",
        "C:\Program Files (x86)\think-cell\ppttc.exe",
        "$env:LOCALAPPDATA\think-cell\ppttc.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Get-Item -LiteralPath $candidate)
        }
    }
    return $null
}

function Get-MemberSurface {
    param([object] $Object)
    if ($null -eq $Object) { return @() }
    try {
        return @(
            $Object |
                Get-Member |
                Where-Object { $_.MemberType -in @("Method", "Property") } |
                Sort-Object Name |
                ForEach-Object {
                    [ordered]@{
                        name = $_.Name
                        member_type = [string] $_.MemberType
                        definition = [string] $_.Definition
                    }
                }
        )
    } catch {
        return @()
    }
}

function Add-DispatchProbeType {
    $code = @"
using System;
using System.Runtime.InteropServices;

namespace SimCorpThinkCellHiddenProbe {
  [ComImport, Guid("00020400-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IDispatch {
    [PreserveSig] int GetTypeInfoCount(out uint pctinfo);
    [PreserveSig] int GetTypeInfo(uint iTInfo, uint lcid, out IntPtr ppTInfo);
    [PreserveSig] int GetIDsOfNames(
      ref Guid riid,
      [MarshalAs(UnmanagedType.LPArray, ArraySubType=UnmanagedType.LPWStr, SizeParamIndex=2)] string[] rgszNames,
      uint cNames,
      uint lcid,
      [Out, MarshalAs(UnmanagedType.LPArray, SizeParamIndex=2)] int[] rgDispId);
    [PreserveSig] int Invoke(
      int dispIdMember,
      ref Guid riid,
      uint lcid,
      ushort wFlags,
      IntPtr pDispParams,
      IntPtr pVarResult,
      IntPtr pExcepInfo,
      IntPtr puArgErr);
  }

  public class DispatchProbeResult {
    public string Name;
    public int HResult;
    public string HResultHex;
    public int DispId;
    public bool Found;
    public string Error;
  }

  public static class DispatchProbe {
    public static DispatchProbeResult GetDispId(object comObj, string name) {
      var result = new DispatchProbeResult();
      result.Name = name;
      result.DispId = -1;
      result.HResult = -1;
      result.HResultHex = "0xffffffff";
      result.Found = false;
      if (comObj == null || String.IsNullOrWhiteSpace(name)) {
        result.Error = "null object or empty name";
        return result;
      }
      IntPtr pDisp = IntPtr.Zero;
      try {
        pDisp = Marshal.GetIDispatchForObject(comObj);
        var dispatch = (IDispatch) Marshal.GetObjectForIUnknown(pDisp);
        Guid iidNull = Guid.Empty;
        string[] names = new string[] { name };
        int[] dispIds = new int[] { -1 };
        int hr = dispatch.GetIDsOfNames(ref iidNull, names, 1, 0, dispIds);
        result.HResult = hr;
        result.HResultHex = unchecked((uint)hr).ToString("x8");
        result.DispId = dispIds[0];
        result.Found = hr >= 0;
      } catch (Exception ex) {
        result.Error = ex.GetType().FullName + ": " + ex.Message;
      } finally {
        if (pDisp != IntPtr.Zero) {
          Marshal.Release(pDisp);
        }
      }
      return result;
    }
  }
}
"@
    try {
        Add-Type -TypeDefinition $code -Language CSharp -ErrorAction Stop | Out-Null
    } catch {
        if ($_.Exception.Message -notmatch "already exists") {
            throw
        }
    }
}

function Get-DispatchRows {
    param(
        [object] $ComObject,
        [string[]] $Names
    )
    $rows = @()
    if ($null -eq $ComObject) { return $rows }
    foreach ($name in @($Names | Where-Object { $_ } | Sort-Object -Unique)) {
        try {
            $probe = [SimCorpThinkCellHiddenProbe.DispatchProbe]::GetDispId($ComObject, $name)
            $rows += [ordered]@{
                name = $probe.Name
                found = [bool] $probe.Found
                dispid = [int] $probe.DispId
                hresult = [int] $probe.HResult
                hresult_hex = [string] $probe.HResultHex
                error = [string] $probe.Error
            }
        } catch {
            $rows += [ordered]@{
                name = $name
                found = $false
                dispid = $null
                hresult = $null
                hresult_hex = $null
                error = $_.Exception.Message
            }
        }
    }
    return $rows
}

function Get-SeedCandidateNames {
    $base = @(
        "CreateChart", "InsertChart", "AddChart", "NewChart",
        "CreateElement", "InsertElement", "AddElement", "NewElement",
        "CreateThinkCellChart", "InsertThinkCellChart", "AddThinkCellChart",
        "ThinkCellInsertChart", "tcInsertChart", "tcCreateChart", "tcAddChart",
        "InsertBarChart", "CreateBarChart", "AddBarChart",
        "InsertColumnChart", "CreateColumnChart", "InsertStackedColumnChart",
        "InsertLineChart", "InsertWaterfallChart", "InsertMekkoChart",
        "InsertGanttChart", "InsertScatterChart", "InsertBubbleChart",
        "InsertTable", "CreateTable", "AddTable",
        "CreateDataTable", "InsertDataTable", "StartTableInsertion",
        "ShowChartGallery", "ShowElementGallery",
        "SetName", "GetName", "SetAutomationName", "GetAutomationName",
        "SetElementName", "GetElementName", "RenameElement",
        "AddRangeData", "AddRangeImage", "CreateUpdate", "Send",
        "PresentationFromTemplate", "PresentationFromTemplateStep3",
        "UpdateBatch", "UpdateBatchStep3", "UpdateChart", "UpdateChartStep3",
        "ImportMekkoGraphicsCharts", "GetMekkoGraphicsXML",
        "LoadStyle", "LoadStyleForRegion", "GetStyleName", "RemoveStyles"
    )
    $families = @("Bar", "Column", "Stacked", "Line", "Area", "Waterfall", "Mekko", "Gantt", "Timeline", "Scatter", "Bubble", "Pie", "Table")
    $verbs = @("Create", "Insert", "Add", "New", "Start", "Show", "Make")
    $suffixes = @("Chart", "Element", "Shape", "Object")
    $names = New-Object System.Collections.Generic.HashSet[string]
    foreach ($item in $base) { [void] $names.Add($item) }
    foreach ($verb in $verbs) {
        foreach ($family in $families) {
            foreach ($suffix in $suffixes) {
                [void] $names.Add("$verb$family$suffix")
                [void] $names.Add("tc$verb$family$suffix")
                [void] $names.Add("ThinkCell$verb$family$suffix")
            }
        }
    }
    return @($names | Sort-Object)
}

function Get-InstallBinaryStrings {
    param([string] $InstallRoot, [int] $Limit)
    $rows = @()
    if (-not $InstallRoot -or -not (Test-Path -LiteralPath $InstallRoot)) { return $rows }
    $priority = @{
        "tcaddin.dll" = 0
        "tcrunxl.exe" = 1
        "tctabimp.exe" = 2
        "tcserver.exe" = 3
        "ppttc.exe" = 4
        "ppttchdl.exe" = 5
        "tcasr.exe" = 6
        "tcindex.exe" = 7
        "tcmail.exe" = 8
        "tcupdate.exe" = 9
        "tcdiag.exe" = 10
        "tcdump.exe" = 11
    }
    $files = @(
        Get-ChildItem -LiteralPath $InstallRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @(".dll", ".exe", ".json", ".xll") }
    ) |
        Sort-Object @{ Expression = {
            $name = $_.Name.ToLowerInvariant()
            if ($priority.ContainsKey($name)) { $priority[$name] } else { 1000 }
        }}, FullName -Unique
    $pattern = "(?i)(think|chart|insert|create|element|gallery|table|automation|datasheet|command|ribbon|addin|range|mekko|waterfall|gantt|timeline|scatter|bubble|presentation|template|name)"
    $seen = New-Object System.Collections.Generic.HashSet[string]
    foreach ($file in $files) {
        if ($rows.Count -ge $Limit) { break }
        try {
            if ($file.Length -gt 120MB) { continue }
            $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
            $texts = @(
                [System.Text.Encoding]::ASCII.GetString($bytes),
                [System.Text.Encoding]::Unicode.GetString($bytes)
            )
            foreach ($text in $texts) {
                foreach ($match in [regex]::Matches($text, "[\u0020-\u007e]{5,180}")) {
                    if ($rows.Count -ge $Limit) { break }
                    $value = $match.Value.Trim()
                    if ($value -notmatch $pattern) { continue }
                    if ($value.Length -gt 180) { continue }
                    $key = "$($file.Name)|$value"
                    if ($seen.Add($key)) {
                        $rows += [ordered]@{
                            file = $file.FullName
                            file_name = $file.Name
                            value = $value
                        }
                    }
                }
            }
        } catch {}
    }
    return $rows
}

function Get-NamesFromStrings {
    param([object[]] $StringRows)
    $names = New-Object System.Collections.Generic.HashSet[string]
    $interesting = "(?i)(Chart|Element|Insert|Create|Automation|Name|Table|Mekko|Gallery|Shape|Data|Range|Slide|Presentation|Template|Waterfall|Gantt|Scatter|Bubble)"
    foreach ($row in $StringRows) {
        $value = [string] $row.value
        foreach ($match in [regex]::Matches($value, "[A-Za-z_][A-Za-z0-9_]{3,80}")) {
            $token = $match.Value
            if ($token -match $interesting) {
                [void] $names.Add($token)
            }
        }
    }
    return @($names | Sort-Object)
}

function Get-ThinkCellRegistryRows {
    $roots = @(
        "HKCU:\Software\Microsoft\Office\PowerPoint\Addins",
        "HKLM:\Software\Microsoft\Office\PowerPoint\Addins",
        "HKLM:\Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins",
        "HKCU:\Software\Microsoft\Office\Excel\Addins",
        "HKLM:\Software\Microsoft\Office\Excel\Addins",
        "HKLM:\Software\WOW6432Node\Microsoft\Office\Excel\Addins",
        "HKCR:\thinkcell.addin",
        "HKCR:\CLSID"
    )
    $rows = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        try {
            $items = if ($root -eq "HKCR:\CLSID") {
                @(Get-ChildItem $root -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "think|cell" } | Select-Object -First 80)
            } else {
                @(Get-ChildItem $root -ErrorAction SilentlyContinue)
            }
            foreach ($item in $items) {
                $path = $item.PSPath
                $text = $item.Name
                try { $props = Get-ItemProperty -LiteralPath $path -ErrorAction Stop } catch { $props = $null }
                if ($props) {
                    $pairs = @()
                    foreach ($prop in $props.PSObject.Properties) {
                        if ($prop.Name -match "^PS") { continue }
                        $pairs += "$($prop.Name)=$($prop.Value)"
                    }
                    $text += " " + ($pairs -join " ")
                }
                if ($text -match "(?i)think|cell|tcaddin|ppttc") {
                    $rows += [ordered]@{ root = $root; path = $item.Name; properties = $text }
                }
            }
        } catch {}
    }
    return $rows
}

function Get-ThinkCellCommandBars {
    param([object] $App, [int] $Limit = 300)
    $rows = @()
    if ($null -eq $App) { return $rows }
    try {
        foreach ($bar in $App.CommandBars) {
            if ($rows.Count -ge $Limit) { break }
            $barName = ""
            try { $barName = [string] $bar.Name } catch {}
            $barText = $barName
            if ($barText -notmatch "(?i)think|cell|tc|chart|table") {
                # Keep scanning controls; many add-in controls live under common bars.
            }
            try {
                foreach ($control in $bar.Controls) {
                    if ($rows.Count -ge $Limit) { break }
                    $caption = ""; $id = $null; $onAction = ""; $tag = ""; $tooltip = ""
                    try { $caption = [string] $control.Caption } catch {}
                    try { $id = [int] $control.Id } catch {}
                    try { $onAction = [string] $control.OnAction } catch {}
                    try { $tag = [string] $control.Tag } catch {}
                    try { $tooltip = [string] $control.TooltipText } catch {}
                    $joined = "$barName $caption $onAction $tag $tooltip"
                    if ($joined -match "(?i)think|cell|tc|chart|table|mekko|waterfall|gantt") {
                        $rows += [ordered]@{
                            bar = $barName
                            caption = $caption
                            id = $id
                            on_action = $onAction
                            tag = $tag
                            tooltip = $tooltip
                        }
                    }
                }
            } catch {}
        }
    } catch {}
    return $rows
}

$result = New-Result
$ppt = $null
$xl = $null

try {
    Add-DispatchProbeType
} catch {
    Add-ErrorRow $result "Add-DispatchProbeType" $_
}

try {
    $os = Get-CimInstance Win32_OperatingSystem
    $result.machine = [ordered]@{
        computer_name = $env:COMPUTERNAME
        user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        os_caption = $os.Caption
        os_version = $os.Version
        powershell = $PSVersionTable.PSVersion.ToString()
    }
} catch {
    Add-ErrorRow $result "machine" $_
}

$installRoot = $null
try {
    $ppttc = Find-PpttcExe
    $installRoot = if ($ppttc) { Split-Path -Parent $ppttc.FullName } else { $null }
    $result.thinkcell = [ordered]@{
        ppttc_path = if ($ppttc) { $ppttc.FullName } else { $null }
        install_root = $installRoot
        ppttc_version = if ($ppttc) { [System.Diagnostics.FileVersionInfo]::GetVersionInfo($ppttc.FullName).ProductVersion } else { $null }
    }
} catch {
    Add-ErrorRow $result "thinkcell" $_
}

try {
    $result.registry = @(Get-ThinkCellRegistryRows)
} catch {
    Add-ErrorRow $result "registry" $_
}

$binaryNames = @()
try {
    $result.binary_string_hits = @(Get-InstallBinaryStrings $installRoot $MaxBinaryStrings)
    $binaryNames = @(Get-NamesFromStrings $result.binary_string_hits)
} catch {
    Add-ErrorRow $result "binary_strings" $_
}

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $tcPp = $ppt.COMAddIns.Item("thinkcell.addin").Object
    $result.visible_members.powerpoint_addin = @(Get-MemberSurface $tcPp)
    $result.command_bars = @(Get-ThinkCellCommandBars $ppt)

    $knownPpt = @($result.visible_members.powerpoint_addin | ForEach-Object { $_.name })
    $candidates = @((Get-SeedCandidateNames) + $binaryNames + $knownPpt | Where-Object { $_ } | Sort-Object -Unique | Select-Object -First $MaxDispatchCandidates)
    $result.dispatch_name_probe.powerpoint_addin = @(Get-DispatchRows $tcPp $candidates)
} catch {
    Add-ErrorRow $result "powerpoint_dispatch_probe" $_
} finally {
    if ($ppt) {
        try { $ppt.Quit() | Out-Null } catch {}
    }
}

try {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false
    $tcXl = $xl.COMAddIns.Item("thinkcell.addin").Object
    $result.visible_members.excel_addin = @(Get-MemberSurface $tcXl)
    $knownXl = @($result.visible_members.excel_addin | ForEach-Object { $_.name })
    $candidatesXl = @((Get-SeedCandidateNames) + $binaryNames + $knownXl | Where-Object { $_ } | Sort-Object -Unique | Select-Object -First $MaxDispatchCandidates)
    $result.dispatch_name_probe.excel_addin = @(Get-DispatchRows $tcXl $candidatesXl)
    try {
        $update = $tcXl.CreateUpdate()
        $result.visible_members.excel_update = @(Get-MemberSurface $update)
        $knownUpdate = @($result.visible_members.excel_update | ForEach-Object { $_.name })
        $result.dispatch_name_probe.excel_update = @(Get-DispatchRows $update @((Get-SeedCandidateNames) + $binaryNames + $knownUpdate | Sort-Object -Unique | Select-Object -First $MaxDispatchCandidates))
    } catch {
        Add-ErrorRow $result "excel_create_update_for_dispatch_probe" $_
    }
} catch {
    Add-ErrorRow $result "excel_dispatch_probe" $_
} finally {
    if ($xl) {
        try { $xl.Quit() | Out-Null } catch {}
    }
}

try {
    $ppFound = @($result.dispatch_name_probe.powerpoint_addin | Where-Object { $_.found })
    $xlFound = @($result.dispatch_name_probe.excel_addin | Where-Object { $_.found })
    $upFound = @($result.dispatch_name_probe.excel_update | Where-Object { $_.found })
    $constructorPattern = "(?i)^(Create|Insert|Add|New|Make).*(Chart|Element|Shape|Object)$|^(tc|ThinkCell)(Create|Insert|Add).*(Chart|Element|Shape|Object)$"
    $constructorLike = @(
        $ppFound | Where-Object { $_.name -match $constructorPattern }
        $xlFound | Where-Object { $_.name -match $constructorPattern }
        $upFound | Where-Object { $_.name -match $constructorPattern }
    )
    $result.candidate_summary = [ordered]@{
        binary_string_hit_count = @($result.binary_string_hits).Count
        binary_candidate_name_count = @($binaryNames).Count
        command_bar_hit_count = @($result.command_bars).Count
        powerpoint_found_name_count = @($ppFound).Count
        excel_addin_found_name_count = @($xlFound).Count
        excel_update_found_name_count = @($upFound).Count
        constructor_like_found = @($constructorLike | ForEach-Object { $_.name } | Sort-Object -Unique)
        ui_like_found = @($ppFound | Where-Object { $_.name -match "ShowChartGallery|StartTableInsertion" } | ForEach-Object { $_.name } | Sort-Object -Unique)
    }
    $result.verdict = [ordered]@{
        hidden_headless_chart_constructor_found = @($constructorLike).Count -gt 0
        conclusion = if (@($constructorLike).Count -gt 0) {
            "Candidate constructor names resolved through IDispatch. They still require disposable-deck invocation proof before use."
        } else {
            "No headless chart constructor name resolved through IDispatch. Exposed creation-adjacent names remain UI-only or update-existing-element lanes."
        }
        production_implication = "Do not promote any hidden surface without a disposable deck proof: create, name, bind, save, reopen, render, and no repair prompt."
    }
} catch {
    Add-ErrorRow $result "summary" $_
}

$json = $result | ConvertTo-Json -Depth 12
if ($OutputPath) {
    try {
        $parent = Split-Path -Parent $OutputPath
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)
    } catch {
        Add-ErrorRow $result "write_output" $_
        $json = $result | ConvertTo-Json -Depth 12
    }
}
$json
