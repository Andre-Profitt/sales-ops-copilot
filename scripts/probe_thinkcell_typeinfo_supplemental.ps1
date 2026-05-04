<#
Supplemental dispatch enumeration: IDispatchEx + Step1/Step2 invoke test.

Two orthogonal questions vs the existing typeinfo probe:

1. IDispatchEx::GetNextDispID — different from ITypeInfo. ITypeInfo enumerates
   what the typelib exports; GetNextDispID enumerates every DISPID the
   *implementation* responds to, including DISPIDs deliberately excluded from
   the typelib export. The Step1/Step2 family likely lives there.

2. Explicit invoke of *Step1/*Step2 names that the existing hidden-surface
   probe found resolvable via GetIDsOfNames but typeinfo did not enumerate.
   Test whether they accept zero-args calls (= cheap behavioral probe) and
   capture the HRESULT/exception details.

Read-only. Late-bound zero-arg invocation only — no parameters supplied,
which means the methods either error out (DISP_E_PARAMNOTOPTIONAL etc.) or
fail safely. We do not pass payloads.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-typeinfo-supplemental-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        targets = @()
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

namespace TcDispEx {

    [ComImport]
    [Guid("a6ef9860-c720-11d0-9337-00a0c90dcaa9")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDispatchEx {
        [PreserveSig] int GetTypeInfoCount(out uint pctinfo);
        [PreserveSig] int GetTypeInfo(uint iTInfo, uint lcid, out IntPtr ppTInfo);
        [PreserveSig] int GetIDsOfNames(ref Guid riid, [MarshalAs(UnmanagedType.LPArray, ArraySubType=UnmanagedType.LPWStr)] string[] rgszNames, uint cNames, uint lcid, [Out] int[] rgDispId);
        [PreserveSig] int Invoke(int dispIdMember, ref Guid riid, uint lcid, ushort wFlags, IntPtr pDispParams, IntPtr pVarResult, IntPtr pExcepInfo, IntPtr puArgErr);
        [PreserveSig] int GetDispID([MarshalAs(UnmanagedType.LPWStr)] string bstrName, uint grfdex, out int pid);
        [PreserveSig] int InvokeEx(int id, uint lcid, ushort wFlags, IntPtr pdp, IntPtr pvarRes, IntPtr pei, IntPtr pspCaller);
        [PreserveSig] int DeleteMemberByName([MarshalAs(UnmanagedType.LPWStr)] string bstrName, uint grfdex);
        [PreserveSig] int DeleteMemberByDispID(int id);
        [PreserveSig] int GetMemberProperties(int id, uint grfdexFetch, out uint pgrfdex);
        [PreserveSig] int GetMemberName(int id, [MarshalAs(UnmanagedType.BStr)] out string pbstrName);
        [PreserveSig] int GetNextDispID(uint grfdex, int id, out int pid);
        [PreserveSig] int GetNameSpaceParent([MarshalAs(UnmanagedType.IUnknown)] out object ppunk);
    }

    public class DispEnt {
        public int DispId;
        public string Name;
        public uint Properties;
    }
    public class DispExResult {
        public bool QueriedOk;
        public string Error;
        public List<DispEnt> Entries = new List<DispEnt>();
    }

    public static class DispEx {
        public const uint fdexEnumDefault = 1;
        public const uint fdexEnumAll = 2;
        public const int DISPID_STARTENUM = -1;
        public const int S_OK = 0;
        public const int S_FALSE = 1;

        public static DispExResult Enumerate(object obj) {
            var r = new DispExResult();
            if (obj == null) { r.Error = "null"; return r; }
            try {
                var dx = obj as IDispatchEx;
                if (dx == null) {
                    r.QueriedOk = false;
                    r.Error = "QueryInterface IDispatchEx not supported (cast returned null)";
                    return r;
                }
                r.QueriedOk = true;
                int id = DISPID_STARTENUM;
                int safety = 0;
                while (safety < 5000) {
                    int next;
                    int hr = dx.GetNextDispID(fdexEnumAll, id, out next);
                    if (hr == S_FALSE) break;
                    if (hr != S_OK) { r.Error = "GetNextDispID hr=0x" + hr.ToString("X8") + " at id=" + id; break; }
                    string name = null;
                    try { dx.GetMemberName(next, out name); } catch {}
                    uint props = 0;
                    try { dx.GetMemberProperties(next, 0xFFFFFFFF, out props); } catch {}
                    r.Entries.Add(new DispEnt { DispId = next, Name = name, Properties = props });
                    id = next;
                    safety++;
                }
                return r;
            } catch (Exception ex) {
                r.Error = ex.GetType().Name + ": " + ex.Message;
                return r;
            }
        }

        public static int GetDispIdFor(object obj, string name) {
            if (obj == null) return -1;
            try {
                var dx = obj as IDispatchEx;
                if (dx == null) return -2;
                int id;
                int hr = dx.GetDispID(name, 0, out id);
                return hr == 0 ? id : -3;
            } catch {
                return -4;
            }
        }
    }
}
"@
try {
    Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop
} catch {
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

# Acquire the 3 add-in objects
$ppt = $null; $xl = $null
$tcPp = $null; $tcXl = $null; $tcUpdate = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $a = $ppt.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if ($a) { $tcPp = $a.Object }
} catch { Add-ErrorRow -Result $result -Where "ppt:create" -Err $_ }

try {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false
    $xl.DisplayAlerts = $false
    $a = $xl.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if ($a) {
        $tcXl = $a.Object
        try { $tcUpdate = $tcXl.CreateUpdate() } catch { Add-ErrorRow -Result $result -Where "tcUpdate" -Err $_ }
    }
} catch { Add-ErrorRow -Result $result -Where "xl:create" -Err $_ }

# Step1/Step2 candidate names — from the existing hidden-surface-probe results
$stepCandidates = @(
    "PresentationFromTemplate", "PresentationFromTemplateStep1", "PresentationFromTemplateStep2",
    "UpdateChart", "UpdateChartStep1", "UpdateChartStep2",
    "UpdateBatch", "UpdateBatchStep1", "UpdateBatchStep2",
    "LoadStyle", "LoadStyleStep1", "LoadStyleStep2",
    "LoadStyleForRegion", "LoadStyleForRegionStep1", "LoadStyleForRegionStep2",
    "GetStyleName", "GetStyleNameStep1", "GetStyleNameStep2",
    "RemoveStyles", "RemoveStylesStep1", "RemoveStylesStep2"
)

function Probe-Target {
    param([string] $Label, [object] $Object)
    $entry = [ordered]@{
        label = $Label
        object_type = if ($Object) { $Object.GetType().FullName } else { $null }
        dispatchex = $null
        step_invoke = @()
    }
    if ($null -eq $Object) { $entry.error = "null"; return $entry }

    # IDispatchEx::GetNextDispID
    $dxr = [TcDispEx.DispEx]::Enumerate($Object)
    $entry.dispatchex = [ordered]@{
        queried_ok = $dxr.QueriedOk
        error = $dxr.Error
        entry_count = $dxr.Entries.Count
        entries = @($dxr.Entries | ForEach-Object { [ordered]@{ dispid = $_.DispId; name = $_.Name; properties = $_.Properties } })
    }

    # Step1/Step2 explicit name resolution + zero-arg invoke
    foreach ($name in $stepCandidates) {
        $rec = [ordered]@{ name = $name; dispid = $null; resolves_via_dispex = $false; resolves_via_late = $false; invoke_error = $null; invoke_hresult = $null }
        # GetDispID via IDispatchEx
        $did = [TcDispEx.DispEx]::GetDispIdFor($Object, $name)
        $rec.dispid = $did
        $rec.resolves_via_dispex = ($did -ge 0)
        # Late-bound zero-arg invoke (will likely fail with PARAMNOTOPTIONAL — that's fine)
        try {
            $type = $Object.GetType()
            $null = $type.InvokeMember($name, [System.Reflection.BindingFlags]::InvokeMethod, $null, $Object, @())
            $rec.resolves_via_late = $true
            $rec.invoke_error = "succeeded with no args (unexpected)"
        } catch [System.Runtime.InteropServices.COMException] {
            $rec.resolves_via_late = $true
            $rec.invoke_hresult = "0x" + $_.Exception.HResult.ToString("X8")
            $rec.invoke_error = $_.Exception.Message
        } catch [System.Reflection.TargetInvocationException] {
            $rec.resolves_via_late = $true
            $rec.invoke_hresult = if ($_.Exception.InnerException) { "0x" + $_.Exception.InnerException.HResult.ToString("X8") } else { $null }
            $rec.invoke_error = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
        } catch [System.MissingMemberException] {
            $rec.resolves_via_late = $false
            $rec.invoke_error = "MissingMember (DISP_E_UNKNOWNNAME)"
        } catch {
            $rec.invoke_error = $_.Exception.GetType().Name + ": " + $_.Exception.Message
            $rec.invoke_hresult = if ($_.Exception.HResult) { "0x" + $_.Exception.HResult.ToString("X8") } else { $null }
        }
        $entry.step_invoke += $rec
    }
    return $entry
}

$result.targets += (Probe-Target -Label "tcPpAddIn" -Object $tcPp)
$result.targets += (Probe-Target -Label "tcXlAddIn" -Object $tcXl)
$result.targets += (Probe-Target -Label "tcUpdate" -Object $tcUpdate)

# Verdict
$anyDispEx = $false
$totalDispExEntries = 0
$dispexNovel = @()
$documented = @(
    "QueryInterface","AddRef","Release","GetTypeInfoCount","GetTypeInfo","GetIDsOfNames","Invoke",
    "ActivateAddIn","IsAddInActive","LoadStyle","LoadStyleForRegion","RemoveStyles",
    "GetMekkoGraphicsXML","ImportMekkoGraphicsCharts","StartTableInsertion","GetStyleName",
    "ShowChartGallery","BainToolboxRectangles","BainToolboxApplyShift",
    "PresentationFromTemplateStep3","UpdateChartStep3","UpdateBatchStep3",
    "PresentationFromTemplate","UpdateChart","CreateUpdate",
    "AddRangeData","AddRangeImage","Send"
)
foreach ($t in $result.targets) {
    if ($t.dispatchex.queried_ok) {
        $anyDispEx = $true
        $totalDispExEntries += $t.dispatchex.entry_count
        foreach ($e in $t.dispatchex.entries) {
            if ($e.name -and $documented -notcontains $e.name) {
                $dispexNovel += [ordered]@{ target = $t.label; name = $e.name; dispid = $e.dispid; props = $e.properties }
            }
        }
    }
}
$step1Resolves = @()
$step2Resolves = @()
foreach ($t in $result.targets) {
    foreach ($si in $t.step_invoke) {
        if ($si.name -match "Step1$" -and $si.resolves_via_late) { $step1Resolves += [ordered]@{ target = $t.label; name = $si.name; dispid = $si.dispid; hr = $si.invoke_hresult; err = $si.invoke_error } }
        if ($si.name -match "Step2$" -and $si.resolves_via_late) { $step2Resolves += [ordered]@{ target = $t.label; name = $si.name; dispid = $si.dispid; hr = $si.invoke_hresult; err = $si.invoke_error } }
    }
}
$result.verdict.any_dispatchex_supported = $anyDispEx
$result.verdict.dispatchex_total_entries = $totalDispExEntries
$result.verdict.dispatchex_novel_count = $dispexNovel.Count
$result.verdict.dispatchex_novel = $dispexNovel
$result.verdict.step1_resolves = $step1Resolves
$result.verdict.step2_resolves = $step2Resolves

# Cleanup
if ($tcUpdate) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcUpdate) | Out-Null } catch {} }
if ($tcXl) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcXl) | Out-Null } catch {} }
if ($tcPp) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcPp) | Out-Null } catch {} }
if ($xl) { try { $xl.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null } catch {} }
if ($ppt) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
