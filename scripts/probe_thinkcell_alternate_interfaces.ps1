<#
QueryInterface against well-known COM IIDs on think-cell add-in objects.

For each of tcPpAddIn, tcXlAddIn, tcUpdate (all three known to expose
ITypeInfo per the prior probe), call QueryInterface for a list of
well-known IIDs. Each successful QI = a new code surface we can call.

Of particular interest:
- IConnectionPointContainer: does think-cell fire events back?
- IPersist*: serialization hooks
- IProvideClassInfo*: additional type-info / class metadata

Read-only: QueryInterface only, no method invocation. Each successful
QI just records the fact + the resulting object's runtime type.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-alternate-interfaces-probe/v1"
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

namespace TcAltIfaces {

    public class IfaceProbeResult {
        public string Name;
        public string Iid;
        public bool Supported;
        public string ResolvedTypeName;
        public string Error;
    }

    public class TargetResult {
        public string Label;
        public string ObjectType;
        public List<IfaceProbeResult> Interfaces = new List<IfaceProbeResult>();
        public List<string> ConnectionPointIids = new List<string>();
        public string ConnectionPointError;
    }

    [ComImport]
    [Guid("B196B284-BAB4-101A-B69C-00AA00341D07")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IConnectionPointContainer {
        [PreserveSig] int EnumConnectionPoints(out IntPtr ppEnum);
        [PreserveSig] int FindConnectionPoint(ref Guid riid, out IntPtr ppCP);
    }

    [ComImport]
    [Guid("B196B287-BAB4-101A-B69C-00AA00341D07")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IEnumConnectionPoints {
        [PreserveSig] int Next(uint cConnections, [Out] IntPtr[] ppCP, out uint pcFetched);
        [PreserveSig] int Skip(uint cConnections);
        [PreserveSig] int Reset();
        [PreserveSig] int Clone(out IntPtr ppEnum);
    }

    [ComImport]
    [Guid("B196B286-BAB4-101A-B69C-00AA00341D07")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IConnectionPoint {
        [PreserveSig] int GetConnectionInterface(out Guid pIID);
        [PreserveSig] int GetConnectionPointContainer(out IntPtr ppCPC);
        [PreserveSig] int Advise([MarshalAs(UnmanagedType.IUnknown)] object pUnkSink, out uint pdwCookie);
        [PreserveSig] int Unadvise(uint dwCookie);
        [PreserveSig] int EnumConnections(out IntPtr ppEnum);
    }

    public static class Probe {
        // Well-known IIDs to QueryInterface (string[] pairs because tuple syntax not in older Add-Type compiler)
        public static readonly string[][] CandidateIids = new string[][] {
            new string[] { "IUnknown",                  "00000000-0000-0000-C000-000000000046" },
            new string[] { "IDispatch",                 "00020400-0000-0000-C000-000000000046" },
            new string[] { "IDispatchEx",               "A6EF9860-C720-11D0-9337-00A0C90DCAA9" },
            new string[] { "ITypeInfo",                 "00020401-0000-0000-C000-000000000046" },
            new string[] { "IConnectionPointContainer", "B196B284-BAB4-101A-B69C-00AA00341D07" },
            new string[] { "IProvideClassInfo",         "B196B283-BAB4-101A-B69C-00AA00341D07" },
            new string[] { "IProvideClassInfo2",        "A6BC3AC0-DBAA-11CE-9DE3-00AA004BB851" },
            new string[] { "IPersist",                  "0000010C-0000-0000-C000-000000000046" },
            new string[] { "IPersistStream",            "00000109-0000-0000-C000-000000000046" },
            new string[] { "IPersistStreamInit",        "7FD52380-4E07-101B-AE2D-08002B2EC713" },
            new string[] { "IPersistStorage",           "0000010A-0000-0000-C000-000000000046" },
            new string[] { "IPersistFile",              "0000010B-0000-0000-C000-000000000046" },
            new string[] { "IPersistMemory",            "BD1AE5E0-A6AE-11CE-BD37-504200C10000" },
            new string[] { "IPersistPropertyBag",       "37D84F60-42CB-11CE-8135-00AA004BB851" },
            new string[] { "IObjectSafety",             "CB5BDC81-93C1-11CF-8F20-00805F2CD064" },
            new string[] { "IPropertyNotifySink",       "9BFBBC02-EFF1-101A-84ED-00AA00341D07" },
            new string[] { "IPropertyBag",              "55272A00-42CB-11CE-8135-00AA004BB851" },
            new string[] { "ISupportErrorInfo",         "DF0B3D60-548F-101B-8E65-08002B2BD119" },
            new string[] { "IClientSecurity",           "0000013D-0000-0000-C000-000000000046" },
            new string[] { "IServerSecurity",           "0000013E-0000-0000-C000-000000000046" },
            new string[] { "IExternalConnection",       "00000019-0000-0000-C000-000000000046" },
            new string[] { "IRunnableObject",           "00000126-0000-0000-C000-000000000046" },
            new string[] { "IViewObject",               "0000010D-0000-0000-C000-000000000046" },
            new string[] { "IOleObject",                "00000112-0000-0000-C000-000000000046" },
            new string[] { "ICustomDoc",                "3050F3F0-98B5-11CF-BB82-00AA00BDCE0B" }
        };

        public static List<IfaceProbeResult> ProbeOne(object obj) {
            var results = new List<IfaceProbeResult>();
            if (obj == null) return results;
            IntPtr pUnk = Marshal.GetIUnknownForObject(obj);
            if (pUnk == IntPtr.Zero) return results;
            try {
                foreach (var c in CandidateIids) {
                    var rec = new IfaceProbeResult { Name = c[0], Iid = c[1] };
                    try {
                        Guid iid = new Guid(c[1]);
                        IntPtr p = IntPtr.Zero;
                        int hr = Marshal.QueryInterface(pUnk, ref iid, out p);
                        if (hr == 0 && p != IntPtr.Zero) {
                            rec.Supported = true;
                            try {
                                object o = Marshal.GetObjectForIUnknown(p);
                                rec.ResolvedTypeName = o != null ? o.GetType().FullName : null;
                            } catch (Exception ex) {
                                rec.ResolvedTypeName = "GetObjectForIUnknown_failed: " + ex.Message;
                            }
                            Marshal.Release(p);
                        } else {
                            rec.Supported = false;
                            rec.Error = "hr=0x" + hr.ToString("X8");
                        }
                    } catch (Exception ex) {
                        rec.Error = ex.GetType().Name + ": " + ex.Message;
                    }
                    results.Add(rec);
                }
            } finally {
                Marshal.Release(pUnk);
            }
            return results;
        }

        public static List<string> EnumerateConnectionPoints(object obj, out string err) {
            err = null;
            var ids = new List<string>();
            if (obj == null) { err = "null"; return ids; }
            IConnectionPointContainer cpc = obj as IConnectionPointContainer;
            if (cpc == null) { err = "not_supported"; return ids; }
            try {
                IntPtr pEnum;
                int hr = cpc.EnumConnectionPoints(out pEnum);
                if (hr != 0 || pEnum == IntPtr.Zero) { err = "EnumCPs hr=0x" + hr.ToString("X8"); return ids; }
                try {
                    object enumObj = Marshal.GetObjectForIUnknown(pEnum);
                    var en = enumObj as IEnumConnectionPoints;
                    if (en == null) { err = "enum cast failed"; return ids; }
                    int safety = 0;
                    while (safety < 100) {
                        IntPtr[] arr = new IntPtr[1];
                        uint fetched;
                        hr = en.Next(1, arr, out fetched);
                        if (hr != 0 || fetched == 0) break;
                        try {
                            object cpObj = Marshal.GetObjectForIUnknown(arr[0]);
                            var cp = cpObj as IConnectionPoint;
                            if (cp != null) {
                                Guid pIid;
                                if (cp.GetConnectionInterface(out pIid) == 0) {
                                    ids.Add(pIid.ToString());
                                }
                            }
                        } finally {
                            Marshal.Release(arr[0]);
                        }
                        safety++;
                    }
                } finally {
                    Marshal.Release(pEnum);
                }
            } catch (Exception ex) {
                err = ex.GetType().Name + ": " + ex.Message;
            }
            return ids;
        }
    }
}
"@
try { Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop } catch {
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

function Probe-Target {
    param([string] $Label, [object] $Obj)
    $entry = [ordered]@{
        label = $Label
        object_type = if ($Obj) { $Obj.GetType().FullName } else { $null }
        interfaces = @()
        connection_points = @()
        cp_error = $null
    }
    if ($null -eq $Obj) { $entry.error = "null"; return $entry }
    $ifaces = [TcAltIfaces.Probe]::ProbeOne($Obj)
    foreach ($i in $ifaces) {
        $entry.interfaces += [ordered]@{
            name = $i.Name
            iid = $i.Iid
            supported = $i.Supported
            resolved_type = $i.ResolvedTypeName
            error = $i.Error
        }
    }
    $cpErr = $null
    $cps = [TcAltIfaces.Probe]::EnumerateConnectionPoints($Obj, [ref]$cpErr)
    $entry.connection_points = @($cps)
    $entry.cp_error = $cpErr
    return $entry
}

$result.targets += (Probe-Target -Label "tcPpAddIn" -Obj $tcPp)
$result.targets += (Probe-Target -Label "tcXlAddIn" -Obj $tcXl)
$result.targets += (Probe-Target -Label "tcUpdate" -Obj $tcUpdate)

# Verdict
$supportedSets = @{}
foreach ($t in $result.targets) {
    $supportedSets[$t.label] = @($t.interfaces | Where-Object { $_.supported } | ForEach-Object { $_.name })
}
$result.verdict.per_target_supported = $supportedSets
$result.verdict.connection_points_per_target = @{}
foreach ($t in $result.targets) {
    $result.verdict.connection_points_per_target[$t.label] = $t.connection_points
}
$novelInterfaces = @()
foreach ($t in $result.targets) {
    foreach ($i in $t.interfaces) {
        if ($i.supported -and $i.name -ne "IUnknown" -and $i.name -ne "IDispatch") {
            $novelInterfaces += [ordered]@{ target = $t.label; iface = $i.name; iid = $i.iid }
        }
    }
}
$result.verdict.novel_supported_interfaces = $novelInterfaces
$result.verdict.has_connection_points = (
    ($result.targets | ForEach-Object { $_.connection_points.Count } | Measure-Object -Sum).Sum -gt 0
)

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
