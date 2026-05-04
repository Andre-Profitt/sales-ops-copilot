<#
TCLayout.ActiveDocument.1 ProgID probe.

The slide XML reveals chart placeholders use:
  <p:oleObj progId="TCLayout.ActiveDocument.1" .../>

That's a DIFFERENT registered COM component than tcaddin.dll's add-in object.
This probe characterizes it:
- CLSIDFromProgID
- Resolve to InprocServer32 path
- Try to instantiate (CreateObject)
- If created: ITypeInfo enumeration like the addin probe
- QueryInterface for well-known IIDs
- See what dispatch surface it exposes
#>
[CmdletBinding()]
param([string] $OutputPath)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-tclayout-progid-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        progid_resolution = [ordered]@{}
        instance = [ordered]@{}
        typeinfo = [ordered]@{}
        verdict = [ordered]@{}
        errors = @()
    }
}
function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME

# 1. CLSIDFromProgID via registry walk
$progids = @("TCLayout.ActiveDocument.1", "TCLayout.ActiveDocument", "thinkcell.ppttc", "thinkcell.addin", "thinkcell.addin.1")
foreach ($pid in $progids) {
    $entry = [ordered]@{ progid = $pid }
    try {
        $clsidPath = "Registry::HKEY_CLASSES_ROOT\$pid\CLSID"
        if (Test-Path $clsidPath) {
            $entry.clsid = (Get-ItemProperty -LiteralPath $clsidPath -Name "(default)").'(default)'
            $clsidKey = "Registry::HKEY_CLASSES_ROOT\CLSID\$($entry.clsid)"
            if (Test-Path $clsidKey) {
                try { $entry.default = (Get-ItemProperty -LiteralPath $clsidKey -Name "(default)").'(default)' } catch {}
                $inproc = Join-Path $clsidKey "InprocServer32"
                if (Test-Path $inproc) {
                    try { $entry.inproc_server = (Get-ItemProperty -LiteralPath $inproc -Name "(default)").'(default)' } catch {}
                    try { $entry.threading_model = (Get-ItemProperty -LiteralPath $inproc -Name "ThreadingModel" -ErrorAction Stop).ThreadingModel } catch {}
                }
                $localServer = Join-Path $clsidKey "LocalServer32"
                if (Test-Path $localServer) {
                    try { $entry.local_server = (Get-ItemProperty -LiteralPath $localServer -Name "(default)").'(default)' } catch {}
                }
                $vipid = Join-Path $clsidKey "VersionIndependentProgID"
                if (Test-Path $vipid) {
                    try { $entry.version_independent_progid = (Get-ItemProperty -LiteralPath $vipid -Name "(default)").'(default)' } catch {}
                }
                $tlb = Join-Path $clsidKey "TypeLib"
                if (Test-Path $tlb) {
                    try { $entry.typelib = (Get-ItemProperty -LiteralPath $tlb -Name "(default)").'(default)' } catch {}
                }
                $cat = Join-Path $clsidKey "Implemented Categories"
                if (Test-Path $cat) {
                    try { $entry.implemented_categories = @((Get-ChildItem -LiteralPath $cat -ErrorAction SilentlyContinue).Name) } catch {}
                }
            }
        } else {
            $entry.found = $false
        }
    } catch { Add-ErrorRow -Result $result -Where "resolve:$pid" -Err $_ }
    if ($null -eq $entry.found) { $entry.found = $true }
    $result.progid_resolution[$pid] = $entry
}

# 2. Try to instantiate TCLayout.ActiveDocument.1
$tcLayout = $null
try {
    $tcLayout = New-Object -ComObject "TCLayout.ActiveDocument.1"
    $result.instance.created = $true
    $result.instance.com_type = $tcLayout.GetType().FullName
    try {
        $members = @($tcLayout | Get-Member |
            Where-Object { $_.MemberType -in @("Method", "Property") } |
            ForEach-Object {
                [ordered]@{ name = $_.Name; type = [string]$_.MemberType; def = [string]$_.Definition }
            })
        $result.instance.members = $members
    } catch { Add-ErrorRow -Result $result -Where "members" -Err $_ }
} catch {
    $result.instance.created = $false
    Add-ErrorRow -Result $result -Where "create_object" -Err $_
}

# 3. ITypeInfo on TCLayout instance
$cs = @"
using System;
using System.Collections.Generic;
using ITypeInfo = System.Runtime.InteropServices.ComTypes.ITypeInfo;
using TYPEATTR = System.Runtime.InteropServices.ComTypes.TYPEATTR;
using FUNCDESC = System.Runtime.InteropServices.ComTypes.FUNCDESC;
using ComImportAttribute = System.Runtime.InteropServices.ComImportAttribute;
using GuidAttribute = System.Runtime.InteropServices.GuidAttribute;
using InterfaceTypeAttribute = System.Runtime.InteropServices.InterfaceTypeAttribute;
using ComInterfaceType = System.Runtime.InteropServices.ComInterfaceType;
using PreserveSigAttribute = System.Runtime.InteropServices.PreserveSigAttribute;
using Marshal = System.Runtime.InteropServices.Marshal;

namespace TcLProbe {
    [ComImport]
    [Guid("00020400-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IDispatchRaw {
        [PreserveSig] int GetTypeInfoCount(out uint pctinfo);
        [PreserveSig] int GetTypeInfo(uint iTInfo, uint lcid, out ITypeInfo ppTInfo);
    }
    public class FuncEntry { public string Name; public int MemberId; public short ParamCount; public short Flags; public List<string> ParamNames = new List<string>(); }
    public class TIResult {
        public bool HasTypeInfo;
        public uint TypeInfoCount;
        public string TypeName;
        public Guid TypeGuid;
        public int FuncCount;
        public List<FuncEntry> Funcs = new List<FuncEntry>();
        public string Error;
    }
    public static class TI {
        public static TIResult Probe(object obj) {
            var r = new TIResult();
            if (obj == null) { r.Error = "null"; return r; }
            try {
                var disp = obj as IDispatchRaw;
                if (disp == null) { r.Error = "no IDispatch"; return r; }
                uint count;
                int hr = disp.GetTypeInfoCount(out count);
                if (hr != 0) { r.Error = "GetTypeInfoCount hr=0x" + hr.ToString("X8"); return r; }
                r.TypeInfoCount = count;
                if (count == 0) return r;
                ITypeInfo ti;
                hr = disp.GetTypeInfo(0, 0, out ti);
                if (hr != 0 || ti == null) { r.Error = "GetTypeInfo hr=0x" + hr.ToString("X8"); return r; }
                r.HasTypeInfo = true;
                string name, doc, helpFile; int helpCtx;
                ti.GetDocumentation(-1, out name, out doc, out helpCtx, out helpFile);
                r.TypeName = name ?? "";
                IntPtr pAttr;
                ti.GetTypeAttr(out pAttr);
                if (pAttr == IntPtr.Zero) { r.Error = "GetTypeAttr null"; return r; }
                try {
                    var attr = (TYPEATTR)Marshal.PtrToStructure(pAttr, typeof(TYPEATTR));
                    r.FuncCount = attr.cFuncs;
                    r.TypeGuid = attr.guid;
                    for (int i = 0; i < attr.cFuncs; i++) {
                        IntPtr pFunc;
                        ti.GetFuncDesc(i, out pFunc);
                        if (pFunc == IntPtr.Zero) continue;
                        try {
                            var fd = (FUNCDESC)Marshal.PtrToStructure(pFunc, typeof(FUNCDESC));
                            var entry = new FuncEntry { MemberId = fd.memid, ParamCount = fd.cParams, Flags = (short)fd.wFuncFlags };
                            int wanted = 1 + fd.cParams;
                            string[] names = new string[wanted];
                            int got;
                            ti.GetNames(fd.memid, names, wanted, out got);
                            if (got > 0) entry.Name = names[0];
                            for (int p = 1; p < got; p++) if (names[p] != null) entry.ParamNames.Add(names[p]);
                            r.Funcs.Add(entry);
                        } finally { ti.ReleaseFuncDesc(pFunc); }
                    }
                } finally { ti.ReleaseTypeAttr(pAttr); }
                return r;
            } catch (Exception ex) { r.Error = ex.GetType().Name + ": " + ex.Message; return r; }
        }
    }
}
"@
try { Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop } catch {
    if ($_.Exception.Message -notmatch "already exists") { Add-ErrorRow -Result $result -Where "Add-Type" -Err $_ }
}

if ($tcLayout) {
    $tip = [TcLProbe.TI]::Probe($tcLayout)
    $result.typeinfo.has_typeinfo = $tip.HasTypeInfo
    $result.typeinfo.typeinfo_count = $tip.TypeInfoCount
    $result.typeinfo.type_name = $tip.TypeName
    $result.typeinfo.type_guid = $tip.TypeGuid.ToString()
    $result.typeinfo.func_count = $tip.FuncCount
    $result.typeinfo.error = $tip.Error
    $result.typeinfo.funcs = @($tip.Funcs | ForEach-Object {
        [ordered]@{
            name = $_.Name; memid = $_.MemberId; params = $_.ParamCount
            flags = $_.Flags; param_names = $_.ParamNames
        }
    })
}

# Cleanup
if ($tcLayout) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcLayout) | Out-Null } catch {} }

# Verdict
$result.verdict.tclayout_clsid = $result.progid_resolution["TCLayout.ActiveDocument.1"].clsid
$result.verdict.tclayout_inproc = $result.progid_resolution["TCLayout.ActiveDocument.1"].inproc_server
$result.verdict.is_separate_dll = ($result.verdict.tclayout_inproc -ne $null -and $result.verdict.tclayout_inproc -notlike "*tcaddin.dll*")
$result.verdict.tclayout_typeinfo_func_count = $result.typeinfo.func_count
$result.verdict.tclayout_type_name = $result.typeinfo.type_name

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
