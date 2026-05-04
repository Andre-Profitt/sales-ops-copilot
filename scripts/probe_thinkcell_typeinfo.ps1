<#
ITypeInfo enumeration probe.

The existing hidden-surface probe used IDispatch::GetIDsOfNames to ask
"does name X resolve to a DISPID". This probe uses the orthogonal
IDispatch::GetTypeInfoCount + GetTypeInfo(0) path — if think-cell's
IDispatch implementation provides an ITypeInfo, we get the *complete*
method/property table including hidden DISPIDs that the candidate-name
scan would never have guessed.

Empirically, the COM registry probe found no registered TypeLib. But a
TypeLib in registry is not the same thing as ITypeInfo from an instance:
some IDispatch implementations build ITypeInfo on the fly. This probe
distinguishes "no registered TypeLib" from "no instance ITypeInfo at all".

Read-only. Does not call Invoke; only enumerates.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-typeinfo-probe/v1"
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
using ITypeInfo = System.Runtime.InteropServices.ComTypes.ITypeInfo;
using TYPEATTR = System.Runtime.InteropServices.ComTypes.TYPEATTR;
using FUNCDESC = System.Runtime.InteropServices.ComTypes.FUNCDESC;
using VARDESC = System.Runtime.InteropServices.ComTypes.VARDESC;
using ComImportAttribute = System.Runtime.InteropServices.ComImportAttribute;
using GuidAttribute = System.Runtime.InteropServices.GuidAttribute;
using InterfaceTypeAttribute = System.Runtime.InteropServices.InterfaceTypeAttribute;
using ComInterfaceType = System.Runtime.InteropServices.ComInterfaceType;
using PreserveSigAttribute = System.Runtime.InteropServices.PreserveSigAttribute;
using Marshal = System.Runtime.InteropServices.Marshal;

namespace TcProbe {

    [ComImport]
    [Guid("00020400-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDispatchRaw {
        [PreserveSig] int GetTypeInfoCount(out uint pctinfo);
        [PreserveSig] int GetTypeInfo(uint iTInfo, uint lcid, out ITypeInfo ppTInfo);
    }

    public class FuncEntry {
        public string Name;
        public int MemberId;
        public short InvokeKind;
        public short ParamCount;
        public short FuncFlags;
        public string Documentation;
        public List<string> ParamNames = new List<string>();
    }

    public class VarEntry {
        public string Name;
        public int MemberId;
        public string Documentation;
    }

    public class TypeInfoResult {
        public bool HasTypeInfo;
        public uint TypeInfoCount;
        public string TypeName;
        public string TypeDocString;
        public Guid TypeGuid;
        public int FuncCount;
        public int VarCount;
        public List<FuncEntry> Funcs = new List<FuncEntry>();
        public List<VarEntry> Vars = new List<VarEntry>();
        public string Error;
    }

    public static class TypeInfoProbe {
        public static TypeInfoResult Probe(object comObj) {
            var r = new TypeInfoResult();
            if (comObj == null) { r.Error = "null"; return r; }
            try {
                var disp = comObj as IDispatchRaw;
                if (disp == null) {
                    r.Error = "QueryInterface(IDispatch) failed via cast";
                    return r;
                }
                uint count;
                int hr = disp.GetTypeInfoCount(out count);
                if (hr != 0) { r.Error = "GetTypeInfoCount hr=0x" + hr.ToString("X8"); return r; }
                r.TypeInfoCount = count;
                if (count == 0) { r.HasTypeInfo = false; return r; }
                ITypeInfo ti;
                hr = disp.GetTypeInfo(0, 0, out ti);
                if (hr != 0 || ti == null) { r.Error = "GetTypeInfo hr=0x" + hr.ToString("X8"); return r; }
                r.HasTypeInfo = true;

                string name, docString, helpFile;
                int helpContext;
                ti.GetDocumentation(-1, out name, out docString, out helpContext, out helpFile);
                r.TypeName = name ?? "";
                r.TypeDocString = docString ?? "";

                IntPtr pAttr;
                ti.GetTypeAttr(out pAttr);
                if (pAttr == IntPtr.Zero) { r.Error = "GetTypeAttr null"; return r; }
                try {
                    var attr = (TYPEATTR)Marshal.PtrToStructure(pAttr, typeof(TYPEATTR));
                    r.FuncCount = attr.cFuncs;
                    r.VarCount = attr.cVars;
                    r.TypeGuid = attr.guid;

                    for (int i = 0; i < attr.cFuncs; i++) {
                        IntPtr pFunc;
                        ti.GetFuncDesc(i, out pFunc);
                        if (pFunc == IntPtr.Zero) continue;
                        try {
                            var fd = (FUNCDESC)Marshal.PtrToStructure(pFunc, typeof(FUNCDESC));
                            var entry = new FuncEntry {
                                MemberId = fd.memid,
                                InvokeKind = (short)fd.invkind,
                                ParamCount = fd.cParams,
                                FuncFlags = (short)fd.wFuncFlags
                            };
                            int wanted = 1 + fd.cParams;
                            string[] names = new string[wanted];
                            int got;
                            ti.GetNames(fd.memid, names, wanted, out got);
                            if (got > 0) entry.Name = names[0];
                            for (int pi = 1; pi < got; pi++) {
                                if (names[pi] != null) entry.ParamNames.Add(names[pi]);
                            }
                            try {
                                string fname, fdoc, fhelp;
                                int fhc;
                                ti.GetDocumentation(fd.memid, out fname, out fdoc, out fhc, out fhelp);
                                entry.Documentation = fdoc;
                            } catch {}
                            r.Funcs.Add(entry);
                        } finally {
                            ti.ReleaseFuncDesc(pFunc);
                        }
                    }
                    for (int i = 0; i < attr.cVars; i++) {
                        IntPtr pVar;
                        ti.GetVarDesc(i, out pVar);
                        if (pVar == IntPtr.Zero) continue;
                        try {
                            var vd = (VARDESC)Marshal.PtrToStructure(pVar, typeof(VARDESC));
                            var v = new VarEntry { MemberId = vd.memid };
                            string[] vnames = new string[1];
                            int got;
                            ti.GetNames(vd.memid, vnames, 1, out got);
                            if (got > 0 && vnames[0] != null) v.Name = vnames[0];
                            try {
                                string vname, vdoc, vhelp;
                                int vhc;
                                ti.GetDocumentation(vd.memid, out vname, out vdoc, out vhc, out vhelp);
                                v.Documentation = vdoc;
                            } catch {}
                            r.Vars.Add(v);
                        } finally {
                            ti.ReleaseVarDesc(pVar);
                        }
                    }
                } finally {
                    ti.ReleaseTypeAttr(pAttr);
                }
                return r;
            } catch (Exception ex) {
                r.Error = ex.GetType().Name + ": " + ex.Message;
                return r;
            }
        }
    }
}
"@

try {
    Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop
} catch {
    # Already loaded in this session is fine
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

function Probe-One {
    param([string] $Label, [object] $Object)
    if ($null -eq $Object) {
        return [ordered]@{ label = $Label; error = "null object" }
    }
    $tip = [TcProbe.TypeInfoProbe]::Probe($Object)
    return [ordered]@{
        label = $Label
        object_type = $Object.GetType().FullName
        has_typeinfo = $tip.HasTypeInfo
        typeinfo_count = $tip.TypeInfoCount
        type_name = $tip.TypeName
        type_doc = $tip.TypeDocString
        type_guid = $tip.TypeGuid.ToString()
        func_count = $tip.FuncCount
        var_count = $tip.VarCount
        funcs = @($tip.Funcs | ForEach-Object {
            [ordered]@{
                name = $_.Name
                memid = $_.MemberId
                invkind = $_.InvokeKind
                params = $_.ParamCount
                flags = $_.FuncFlags
                doc = $_.Documentation
                param_names = $_.ParamNames
            }
        })
        vars = @($tip.Vars | ForEach-Object {
            [ordered]@{ name = $_.Name; memid = $_.MemberId; doc = $_.Documentation }
        })
        error = $tip.Error
    }
}

$ppt = $null; $xl = $null
$tcPp = $null; $tcXl = $null; $tcUpdate = $null

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $addin = $ppt.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if ($addin) { $tcPp = $addin.Object }
} catch { Add-ErrorRow -Result $result -Where "ppt:create" -Err $_ }

try {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false
    $xl.DisplayAlerts = $false
    $addinX = $xl.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if ($addinX) {
        $tcXl = $addinX.Object
        try { $tcUpdate = $tcXl.CreateUpdate() } catch { Add-ErrorRow -Result $result -Where "tcUpdate" -Err $_ }
    }
} catch { Add-ErrorRow -Result $result -Where "xl:create" -Err $_ }

$result.targets += (Probe-One -Label "tcPpAddIn" -Object $tcPp)
$result.targets += (Probe-One -Label "tcXlAddIn" -Object $tcXl)
$result.targets += (Probe-One -Label "tcUpdate" -Object $tcUpdate)

$anyTypeInfo = $false
$totalFuncs = 0
$novelFuncs = @()
$documented = @(
    "ActivateAddIn", "BainToolboxApplyShift", "BainToolboxRectangles",
    "GetMekkoGraphicsXML", "GetStyleName", "GetStyleNameStep2",
    "ImportMekkoGraphicsCharts", "IsAddInActive",
    "LoadStyle", "LoadStyleForRegion", "LoadStyleForRegionStep2",
    "LoadStyleStep2", "PresentationFromTemplate", "PresentationFromTemplateStep3",
    "RemoveStyles", "RemoveStylesStep2", "ShowChartGallery", "StartTableInsertion",
    "UpdateBatch", "UpdateBatchStep3", "UpdateChart", "UpdateChartStep3",
    "CreateUpdate", "AddRangeData", "AddRangeImage", "Send"
)
foreach ($t in $result.targets) {
    if ($t.has_typeinfo) {
        $anyTypeInfo = $true
        $totalFuncs += $t.func_count
        foreach ($f in $t.funcs) {
            if ($f.name -and $documented -notcontains $f.name) {
                $novelFuncs += [ordered]@{ target = $t.label; name = $f.name; memid = $f.memid; params = $f.params; doc = $f.doc }
            }
        }
    }
}
$result.verdict.any_typeinfo_exposed = $anyTypeInfo
$result.verdict.total_funcs_via_typeinfo = $totalFuncs
$result.verdict.novel_funcs_count = $novelFuncs.Count
$result.verdict.novel_funcs = $novelFuncs

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
