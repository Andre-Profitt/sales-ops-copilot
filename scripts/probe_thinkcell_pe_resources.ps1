<#
PE-resource enumeration of tcaddin.dll.

Office add-ins universally embed:
- customUI.xml ribbon definition (the C++ method each onAction callback maps to)
- Dialog templates for chart wizards / data dialogs
- Embedded JSON/XML schemas for serialized chart data
- RT_RCDATA blobs for internal config

The existing hidden-surface probe scanned binary *strings*. PE *resources*
are a separate section, often containing the canonical ribbon XML that
exposes onAction → method mappings the string scan misses.

Read-only. Uses Win32 LoadLibraryEx with LOAD_LIBRARY_AS_DATAFILE so the
DLL is opened as data, not loaded for execution.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [string] $DllPath = "C:\Program Files (x86)\think-cell\arm64\tcaddin.dll",
    [string] $DumpDir,
    [int] $MaxResourcesPerType = 100
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-pe-resources-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        binaries = @()
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
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace TcResProbe {
    public class ResEntry {
        public string TypeName;
        public string ResourceName;
        public int Size;
        public bool Dumped;
        public string DumpPath;
        public string Sha256;
        public string Preview;
        public bool LikelyText;
        public bool LikelyXML;
        public bool LikelyJSON;
    }
    public class ResResult {
        public string Path;
        public string FileVersion;
        public List<string> Types = new List<string>();
        public List<ResEntry> Resources = new List<ResEntry>();
        public string Error;
        public long ModuleHandle;
    }

    public static class PeResources {
        const uint LOAD_LIBRARY_AS_DATAFILE = 0x00000002;
        const uint LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x00000020;

        delegate bool EnumResTypeProc(IntPtr hModule, IntPtr lpType, IntPtr lParam);
        delegate bool EnumResNameProc(IntPtr hModule, IntPtr lpType, IntPtr lpName, IntPtr lParam);

        [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
        static extern IntPtr LoadLibraryExW(string lpFileName, IntPtr hFile, uint dwFlags);
        [DllImport("kernel32.dll")]
        static extern bool FreeLibrary(IntPtr hModule);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
        static extern bool EnumResourceTypesW(IntPtr hModule, EnumResTypeProc lpEnumFunc, IntPtr lParam);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
        static extern bool EnumResourceNamesW(IntPtr hModule, IntPtr lpType, EnumResNameProc lpEnumFunc, IntPtr lParam);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
        static extern IntPtr FindResourceW(IntPtr hModule, IntPtr lpName, IntPtr lpType);
        [DllImport("kernel32.dll")]
        static extern uint SizeofResource(IntPtr hModule, IntPtr hResInfo);
        [DllImport("kernel32.dll")]
        static extern IntPtr LoadResource(IntPtr hModule, IntPtr hResInfo);
        [DllImport("kernel32.dll")]
        static extern IntPtr LockResource(IntPtr hResData);

        static string PtrToResName(IntPtr p) {
            long v = p.ToInt64();
            if (v >= 0 && v < 65536) {
                string wellKnown = "";
                switch (v) {
                    case 1: wellKnown = "RT_CURSOR"; break;
                    case 2: wellKnown = "RT_BITMAP"; break;
                    case 3: wellKnown = "RT_ICON"; break;
                    case 4: wellKnown = "RT_MENU"; break;
                    case 5: wellKnown = "RT_DIALOG"; break;
                    case 6: wellKnown = "RT_STRING"; break;
                    case 7: wellKnown = "RT_FONTDIR"; break;
                    case 8: wellKnown = "RT_FONT"; break;
                    case 9: wellKnown = "RT_ACCELERATOR"; break;
                    case 10: wellKnown = "RT_RCDATA"; break;
                    case 11: wellKnown = "RT_MESSAGETABLE"; break;
                    case 12: wellKnown = "RT_GROUP_CURSOR"; break;
                    case 14: wellKnown = "RT_GROUP_ICON"; break;
                    case 16: wellKnown = "RT_VERSION"; break;
                    case 17: wellKnown = "RT_DLGINCLUDE"; break;
                    case 19: wellKnown = "RT_PLUGPLAY"; break;
                    case 20: wellKnown = "RT_VXD"; break;
                    case 21: wellKnown = "RT_ANICURSOR"; break;
                    case 22: wellKnown = "RT_ANIICON"; break;
                    case 23: wellKnown = "RT_HTML"; break;
                    case 24: wellKnown = "RT_MANIFEST"; break;
                }
                return "#" + v.ToString() + (wellKnown.Length > 0 ? "(" + wellKnown + ")" : "");
            }
            try { return Marshal.PtrToStringUni(p); } catch { return "0x" + v.ToString("X"); }
        }

        public static ResResult Enumerate(string path, string dumpDir, int maxResourcesPerType) {
            var r = new ResResult { Path = path };
            try {
                r.FileVersion = System.Diagnostics.FileVersionInfo.GetVersionInfo(path).FileVersion;
            } catch {}
            IntPtr hMod = LoadLibraryExW(path, IntPtr.Zero, LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE);
            if (hMod == IntPtr.Zero) {
                r.Error = "LoadLibraryEx failed: " + Marshal.GetLastWin32Error();
                return r;
            }
            r.ModuleHandle = hMod.ToInt64();
            try {
                var types = new List<IntPtr>();
                EnumResourceTypesW(hMod, (h, t, lp) => { types.Add(t); return true; }, IntPtr.Zero);
                foreach (var t in types) {
                    string typeName = PtrToResName(t);
                    r.Types.Add(typeName);
                    int n = 0;
                    var localT = t;
                    EnumResourceNamesW(hMod, localT, (h2, t2, name, lp2) => {
                        if (n >= maxResourcesPerType) return false;
                        n++;
                        var entry = new ResEntry { TypeName = typeName, ResourceName = PtrToResName(name) };
                        IntPtr hRes = FindResourceW(hMod, name, localT);
                        if (hRes != IntPtr.Zero) {
                            uint sz = SizeofResource(hMod, hRes);
                            entry.Size = (int)sz;
                            IntPtr hData = LoadResource(hMod, hRes);
                            IntPtr ptr = LockResource(hData);
                            if (ptr != IntPtr.Zero && sz > 0 && sz < 50000000) {
                                byte[] buf = new byte[sz];
                                Marshal.Copy(ptr, buf, 0, (int)sz);
                                using (var sha = System.Security.Cryptography.SHA256.Create()) {
                                    entry.Sha256 = BitConverter.ToString(sha.ComputeHash(buf)).Replace("-", "").ToLowerInvariant();
                                }
                                int previewLen = (int)Math.Min(sz, 600);
                                string ascii = Encoding.UTF8.GetString(buf, 0, previewLen);
                                int printable = 0;
                                foreach (char c in ascii) if ((c >= 32 && c < 127) || c == '\n' || c == '\r' || c == '\t') printable++;
                                bool textyAscii = (ascii.Length > 0 && printable * 100 / ascii.Length > 80);
                                string utf16 = "";
                                if (!textyAscii && previewLen > 1) {
                                    utf16 = Encoding.Unicode.GetString(buf, 0, (previewLen / 2) * 2);
                                    int p2 = 0;
                                    foreach (char c in utf16) if ((c >= 32 && c < 127) || c == '\n' || c == '\r' || c == '\t') p2++;
                                    if (utf16.Length > 0 && p2 * 100 / utf16.Length > 80) {
                                        entry.Preview = utf16;
                                        entry.LikelyText = true;
                                    }
                                } else if (textyAscii) {
                                    entry.Preview = ascii;
                                    entry.LikelyText = true;
                                }
                                if (entry.LikelyText && entry.Preview != null) {
                                    string p = entry.Preview.TrimStart();
                                    if (p.StartsWith("<?xml") || p.StartsWith("<")) entry.LikelyXML = true;
                                    if (p.StartsWith("{") || p.StartsWith("[")) entry.LikelyJSON = true;
                                }
                                if (dumpDir != null) {
                                    try {
                                        Directory.CreateDirectory(dumpDir);
                                        string safeT = typeName.Replace("#","ID").Replace("/","_").Replace("\\","_").Replace("(","_").Replace(")","").Replace(" ","_");
                                        string safeN = entry.ResourceName.Replace("#","ID").Replace("/","_").Replace("\\","_").Replace(" ","_");
                                        string ext = entry.LikelyXML ? ".xml" : (entry.LikelyJSON ? ".json" : (entry.LikelyText ? ".txt" : ".bin"));
                                        string dest = Path.Combine(dumpDir, safeT + "_" + safeN + ext);
                                        File.WriteAllBytes(dest, buf);
                                        entry.Dumped = true;
                                        entry.DumpPath = dest;
                                    } catch (Exception ex) {
                                        entry.DumpPath = "DUMP_ERROR: " + ex.Message;
                                    }
                                }
                            }
                        }
                        r.Resources.Add(entry);
                        return true;
                    }, IntPtr.Zero);
                }
            } finally {
                FreeLibrary(hMod);
            }
            return r;
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

$dllCandidates = @($DllPath)
$dllCandidates += @(
    "C:\Program Files (x86)\think-cell\x86\tcaddin.dll",
    "C:\Program Files (x86)\think-cell\x64\tcaddin.dll",
    "C:\Program Files\think-cell\arm64\tcaddin.dll",
    "C:\Program Files (x86)\think-cell\arm64\ppttc.exe",
    "C:\Program Files (x86)\think-cell\ppttc.exe",
    "C:\Program Files (x86)\think-cell\tcserver.exe"
) | Where-Object { Test-Path -LiteralPath $_ }
$dllCandidates = @($dllCandidates | Sort-Object -Unique | Where-Object { Test-Path -LiteralPath $_ })

if (-not $DumpDir) {
    $DumpDir = Join-Path ([System.IO.Path]::GetDirectoryName($OutputPath)) "dumps"
}

foreach ($dll in $dllCandidates) {
    try {
        $sub = (Split-Path -Leaf $dll) -replace "[^A-Za-z0-9_.-]", "_"
        $perBinaryDump = Join-Path $DumpDir $sub
        $res = [TcResProbe.PeResources]::Enumerate($dll, $perBinaryDump, $MaxResourcesPerType)
        $entry = [ordered]@{
            path = $res.Path
            file_version = $res.FileVersion
            types = $res.Types
            resource_count = $res.Resources.Count
            resources = @($res.Resources | ForEach-Object {
                [ordered]@{
                    type = $_.TypeName
                    name = $_.ResourceName
                    size = $_.Size
                    sha256 = $_.Sha256
                    likely_text = $_.LikelyText
                    likely_xml = $_.LikelyXML
                    likely_json = $_.LikelyJSON
                    dumped = $_.Dumped
                    dump_path = $_.DumpPath
                    preview = if ($_.Preview) { $_.Preview.Substring(0, [Math]::Min(500, $_.Preview.Length)) } else { $null }
                }
            })
            error = $res.Error
        }
        $result.binaries += $entry
    } catch {
        Add-ErrorRow -Result $result -Where "enum:$dll" -Err $_
    }
}

$totalRes = ($result.binaries | ForEach-Object { $_.resource_count } | Measure-Object -Sum).Sum
$xmlRes = @()
foreach ($b in $result.binaries) {
    foreach ($r in $b.resources) {
        if ($r.likely_xml) { $xmlRes += [ordered]@{ binary = (Split-Path -Leaf $b.path); type = $r.type; name = $r.name; size = $r.size; preview = $r.preview } }
    }
}
$result.verdict.binary_count = $result.binaries.Count
$result.verdict.total_resources = $totalRes
$result.verdict.xml_resources_found = $xmlRes.Count
$result.verdict.xml_resources = $xmlRes
$result.verdict.has_customui_xml = ($xmlRes | Where-Object { $_.preview -and ($_.preview -match "customUI|tabs|button|onAction|tglbtn") }).Count -gt 0

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
