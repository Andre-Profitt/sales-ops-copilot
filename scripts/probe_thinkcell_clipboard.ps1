<#
Clipboard format dump probe.

When you copy a think-cell chart in PowerPoint, the clipboard receives
multiple formats — including private formats registered by tcaddin.dll
(typically named "think-cell/*"). These formats contain the canonical
binary serialization of the chart, which is the closest thing to the
"native chart spec" think-cell uses internally.

Requirements:
- Interactive desktop session (cannot run via SSH non-interactive)
- A think-cell chart must already be in the clipboard before invocation

Read-only. The probe only enumerates and dumps clipboard contents; it
does not write to the clipboard or invoke chart code.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [string] $DumpDir,
    [switch] $RequireInteractive
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-clipboard-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        session = [ordered]@{}
        formats = @()
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

# Win32 clipboard API for raw byte access (System.Windows.Forms.Clipboard
# returns marshaled .NET types; raw bytes for private formats need Win32).
$cs = @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace TcClipProbe {
    public class FormatEntry {
        public uint FormatId;
        public string FormatName;
        public string Source;
        public int ByteSize;
        public string Sha256;
        public bool Dumped;
        public string DumpPath;
        public string Preview;
        public bool LikelyText;
        public bool LikelyXML;
        public bool LikelyJSON;
        public bool LikelyOOXML;
        public bool LikelyCFB;
    }
    public class ClipResult {
        public bool Opened;
        public List<FormatEntry> Formats = new List<FormatEntry>();
        public string Error;
    }

    public static class Clip {
        [DllImport("user32.dll", SetLastError=true)]
        static extern bool OpenClipboard(IntPtr hWndNewOwner);
        [DllImport("user32.dll", SetLastError=true)]
        static extern bool CloseClipboard();
        [DllImport("user32.dll", SetLastError=true)]
        static extern uint EnumClipboardFormats(uint format);
        [DllImport("user32.dll", SetLastError=true)]
        static extern int CountClipboardFormats();
        [DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
        static extern int GetClipboardFormatNameW(uint format, StringBuilder lpszFormatName, int cchMaxCount);
        [DllImport("user32.dll", SetLastError=true)]
        static extern IntPtr GetClipboardData(uint uFormat);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern IntPtr GlobalLock(IntPtr hMem);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern bool GlobalUnlock(IntPtr hMem);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern UIntPtr GlobalSize(IntPtr hMem);

        static string FormatNameForId(uint id) {
            switch (id) {
                case 1: return "CF_TEXT";
                case 2: return "CF_BITMAP";
                case 3: return "CF_METAFILEPICT";
                case 4: return "CF_SYLK";
                case 5: return "CF_DIF";
                case 6: return "CF_TIFF";
                case 7: return "CF_OEMTEXT";
                case 8: return "CF_DIB";
                case 9: return "CF_PALETTE";
                case 10: return "CF_PENDATA";
                case 11: return "CF_RIFF";
                case 12: return "CF_WAVE";
                case 13: return "CF_UNICODETEXT";
                case 14: return "CF_ENHMETAFILE";
                case 15: return "CF_HDROP";
                case 16: return "CF_LOCALE";
                case 17: return "CF_DIBV5";
            }
            var sb = new StringBuilder(512);
            int n = GetClipboardFormatNameW(id, sb, sb.Capacity);
            return n > 0 ? sb.ToString() : "<unknown:" + id + ">";
        }

        public static ClipResult Enumerate(string dumpDir, int maxBytesPerFormat) {
            var r = new ClipResult();
            if (!OpenClipboard(IntPtr.Zero)) {
                r.Error = "OpenClipboard failed: " + Marshal.GetLastWin32Error();
                return r;
            }
            r.Opened = true;
            try {
                uint fmt = 0;
                while ((fmt = EnumClipboardFormats(fmt)) != 0) {
                    var e = new FormatEntry { FormatId = fmt, FormatName = FormatNameForId(fmt), Source = "EnumClipboardFormats" };
                    IntPtr hData = GetClipboardData(fmt);
                    if (hData != IntPtr.Zero) {
                        UIntPtr sz = GlobalSize(hData);
                        int size = (int)sz.ToUInt64();
                        e.ByteSize = size;
                        if (size > 0 && size < 100000000) {
                            IntPtr ptr = GlobalLock(hData);
                            if (ptr != IntPtr.Zero) {
                                int copy = Math.Min(size, maxBytesPerFormat);
                                byte[] buf = new byte[copy];
                                try {
                                    Marshal.Copy(ptr, buf, 0, copy);
                                } finally {
                                    GlobalUnlock(hData);
                                }
                                using (var sha = System.Security.Cryptography.SHA256.Create()) {
                                    e.Sha256 = BitConverter.ToString(sha.ComputeHash(buf)).Replace("-", "").ToLowerInvariant();
                                }
                                int previewLen = Math.Min(copy, 400);
                                string ascii = Encoding.UTF8.GetString(buf, 0, previewLen);
                                int printable = 0;
                                foreach (char c in ascii) if ((c >= 32 && c < 127) || c == '\n' || c == '\r' || c == '\t') printable++;
                                if (ascii.Length > 0 && printable * 100 / ascii.Length > 70) {
                                    e.LikelyText = true;
                                    e.Preview = ascii;
                                    string trimmed = ascii.TrimStart();
                                    if (trimmed.StartsWith("<?xml") || trimmed.StartsWith("<")) e.LikelyXML = true;
                                    if (trimmed.StartsWith("{") || trimmed.StartsWith("[")) e.LikelyJSON = true;
                                }
                                // OOXML zip magic: PK\x03\x04
                                if (size >= 4 && buf[0] == 0x50 && buf[1] == 0x4B && buf[2] == 0x03 && buf[3] == 0x04) e.LikelyOOXML = true;
                                // CFB magic: D0 CF 11 E0 A1 B1 1A E1
                                if (size >= 8 && buf[0] == 0xD0 && buf[1] == 0xCF && buf[2] == 0x11 && buf[3] == 0xE0 && buf[4] == 0xA1 && buf[5] == 0xB1 && buf[6] == 0x1A && buf[7] == 0xE1) e.LikelyCFB = true;

                                if (dumpDir != null) {
                                    try {
                                        System.IO.Directory.CreateDirectory(dumpDir);
                                        string safe = e.FormatName.Replace("/","_").Replace("\\","_").Replace(":","_").Replace("<","").Replace(">","").Replace(" ","_");
                                        string ext = e.LikelyOOXML ? ".pptx" : (e.LikelyCFB ? ".cfb" : (e.LikelyXML ? ".xml" : (e.LikelyJSON ? ".json" : (e.LikelyText ? ".txt" : ".bin"))));
                                        string dest = System.IO.Path.Combine(dumpDir, "fmt_" + e.FormatId.ToString() + "_" + safe + ext);
                                        // Re-fetch full bytes for dump (if smaller than max)
                                        IntPtr ptr2 = GlobalLock(hData);
                                        if (ptr2 != IntPtr.Zero) {
                                            try {
                                                byte[] full = new byte[size];
                                                Marshal.Copy(ptr2, full, 0, size);
                                                System.IO.File.WriteAllBytes(dest, full);
                                                e.Dumped = true;
                                                e.DumpPath = dest;
                                            } finally {
                                                GlobalUnlock(hData);
                                            }
                                        }
                                    } catch (Exception ex) {
                                        e.DumpPath = "DUMP_ERROR: " + ex.Message;
                                    }
                                }
                            }
                        }
                    }
                    r.Formats.Add(e);
                }
            } finally {
                CloseClipboard();
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
$result.session.user_interactive = [Environment]::UserInteractive
$result.session.session_name = $env:SESSIONNAME
$result.session.is_console = ($env:SESSIONNAME -eq "Console")

if ($RequireInteractive -and (-not [Environment]::UserInteractive -or $env:SESSIONNAME -ne "Console")) {
    Add-ErrorRow -Result $result -Where "session" -Err "Not running in an interactive desktop session. Run from PowerShell on the VM console after copying a think-cell chart in PowerPoint."
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}

if (-not $DumpDir -and $OutputPath) {
    $DumpDir = Join-Path ([System.IO.Path]::GetDirectoryName($OutputPath)) "dumps"
}

try {
    $clip = [TcClipProbe.Clip]::Enumerate($DumpDir, 10000000)
    foreach ($f in $clip.Formats) {
        $result.formats += [ordered]@{
            id = $f.FormatId
            name = $f.FormatName
            byte_size = $f.ByteSize
            sha256 = $f.Sha256
            likely_text = $f.LikelyText
            likely_xml = $f.LikelyXML
            likely_json = $f.LikelyJSON
            likely_ooxml = $f.LikelyOOXML
            likely_cfb = $f.LikelyCFB
            dumped = $f.Dumped
            dump_path = $f.DumpPath
            preview = $f.Preview
        }
    }
    if ($clip.Error) { Add-ErrorRow -Result $result -Where "clipboard" -Err $clip.Error }
} catch {
    Add-ErrorRow -Result $result -Where "enumerate" -Err $_
}

$tcFormats = @($result.formats | Where-Object { $_.name -match "think|tc/|/tc|thinkcell" })
$ooxmlFormats = @($result.formats | Where-Object { $_.likely_ooxml })
$cfbFormats = @($result.formats | Where-Object { $_.likely_cfb })
$xmlFormats = @($result.formats | Where-Object { $_.likely_xml })
$result.verdict.format_count = $result.formats.Count
$result.verdict.thinkcell_named_formats = $tcFormats
$result.verdict.thinkcell_named_count = $tcFormats.Count
$result.verdict.ooxml_format_count = $ooxmlFormats.Count
$result.verdict.cfb_format_count = $cfbFormats.Count
$result.verdict.xml_format_count = $xmlFormats.Count
$result.verdict.private_format_byte_total = (($result.formats | Where-Object { $_.id -ge 0xC000 } | ForEach-Object { $_.byte_size } | Measure-Object -Sum).Sum)

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
