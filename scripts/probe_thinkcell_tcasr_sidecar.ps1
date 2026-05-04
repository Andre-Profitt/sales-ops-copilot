<#
tcasr.exe sidecar process probe.

think-cell's dev blog ("By Default Different") discloses that tcaddin.dll
communicates with a separate process named tcasr.exe via:
- named mutexes
- Win32 user messages
- shared-memory file backing (named sections)

The existing COM registry / OleViewDotNet / Procmon probes did not
characterize this sidecar. This probe enumerates:

- tcasr* binaries on disk under known install roots
- Currently-running tcasr* processes (PID, parent, start time, command line)
- Top-level windows whose class name or title contains "tc"
- Shared memory section names visible under \BaseNamedObjects
  (only what's reachable without elevation)
- PE static surface of tcasr.exe (version, hash, imports table sample,
  command-like string scan)

Read-only. Does not start, signal, or stop any process.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [int] $MaxBinaryStrings = 600
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-tcasr-sidecar-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        binaries = @()
        processes = @()
        windows = @()
        named_objects = @()
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
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

# 1. Disk enumeration of tcasr* binaries
$roots = @(
    "C:\Program Files\think-cell",
    "C:\Program Files (x86)\think-cell",
    "$env:LOCALAPPDATA\think-cell",
    "$env:APPDATA\think-cell"
)
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    try {
        $hits = Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction Stop |
            Where-Object { $_.Name -match "^tcasr|tcsidecar|tcservice|tcsr" -or $_.Name -eq "tcasr.exe" }
        foreach ($h in $hits) {
            $vi = $h.VersionInfo
            $entry = [ordered]@{
                path = $h.FullName
                size = $h.Length
                file_version = $vi.FileVersion
                product_version = $vi.ProductVersion
                product_name = $vi.ProductName
                company = $vi.CompanyName
                hash_sha256 = (Get-FileHash -LiteralPath $h.FullName -Algorithm SHA256).Hash
                last_write_utc = $h.LastWriteTimeUtc.ToString("o")
            }
            try {
                $bytes = [System.IO.File]::ReadAllBytes($h.FullName)
                $text = [System.Text.Encoding]::ASCII.GetString($bytes)
                $entry.string_hits = [ordered]@{
                    mutex = ([regex]::Matches($text, "(?<![A-Za-z0-9_])(Global\\|Local\\)?tc[A-Z][a-zA-Z0-9_]+(Mutex|Event|Section)")).Count
                    section = ([regex]::Matches($text, "tc[A-Za-z]+(Section|Mapping|Memory|Shared)")).Count
                    pipe = ([regex]::Matches($text, "\\\\\.\\pipe\\tc[A-Za-z0-9_]+")).Count
                    rpc = ([regex]::Matches($text, "(?i)RpcServer|RpcBindingFromStringBinding|RpcStringBindingCompose")).Count
                    com = ([regex]::Matches($text, "(?<![A-Za-z])(CoCreateInstance|CoInitialize|RegisterClassObject)")).Count
                    suspicious_callable = @{}
                }
                $callable = [regex]::Matches($text, "(?<![A-Za-z])(?:Add|Get|Set|Create|Insert|Update|Remove|Show|Hide|Start|Stop|Begin|End|Init|Load|Save|Open|Close|Activate|Send|Receive|Bind|Unbind|Probe|Query|Resolve|Make|Build|Render|Export|Import|Process|Handle|Notify|Fire|Trigger|Dispatch|Forward)[A-Z][a-zA-Z0-9_]{2,32}") |
                    ForEach-Object { $_.Value } | Group-Object | Sort-Object Count -Descending | Select-Object -First $MaxBinaryStrings | ForEach-Object { $_.Name }
                $entry.callable_strings = @($callable | Sort-Object -Unique)
            } catch {
                Add-ErrorRow -Result $result -Where "string_scan:$($h.FullName)" -Err $_
            }
            $result.binaries += $entry
        }
    } catch {
        Add-ErrorRow -Result $result -Where "scan:$root" -Err $_
    }
}

# 2. Currently-running tcasr* processes
try {
    $procs = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.Name -match "^tcasr|tcsidecar|tcservice|tcsr" }
    foreach ($p in $procs) {
        $entry = [ordered]@{
            name = $p.Name
            pid = $p.ProcessId
            parent_pid = $p.ParentProcessId
            command_line = $p.CommandLine
            executable_path = $p.ExecutablePath
            creation_date = $p.CreationDate
            handle_count = $p.HandleCount
            thread_count = $p.ThreadCount
            working_set = $p.WorkingSetSize
        }
        try {
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" -ErrorAction Stop
            $entry.parent_name = $parent.Name
            $entry.parent_path = $parent.ExecutablePath
        } catch {}
        $result.processes += $entry
    }
} catch {
    Add-ErrorRow -Result $result -Where "process_enum" -Err $_
}

# 3. Top-level windows whose class or title contains tc*
$cs = @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace TcWinProbe {
    public class WinEntry {
        public IntPtr Hwnd;
        public string ClassName;
        public string Title;
        public uint ProcessId;
        public uint ThreadId;
    }
    public static class Winum {
        delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
        [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowTextW(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassNameW(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        public static List<WinEntry> Enumerate() {
            var list = new List<WinEntry>();
            EnumWindows((h, l) => {
                var cls = new StringBuilder(256);
                var tit = new StringBuilder(512);
                GetClassNameW(h, cls, cls.Capacity);
                GetWindowTextW(h, tit, tit.Capacity);
                uint pid;
                uint tid = GetWindowThreadProcessId(h, out pid);
                string cs = cls.ToString();
                string ts = tit.ToString();
                if (cs.IndexOf("tc", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    cs.IndexOf("think", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    ts.IndexOf("think-cell", StringComparison.OrdinalIgnoreCase) >= 0) {
                    list.Add(new WinEntry { Hwnd = h, ClassName = cs, Title = ts, ProcessId = pid, ThreadId = tid });
                }
                return true;
            }, IntPtr.Zero);
            return list;
        }
    }
}
"@
try {
    Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop
} catch {
    if ($_.Exception.Message -notmatch "already exists") {
        Add-ErrorRow -Result $result -Where "Add-Type" -Err $_
    }
}
try {
    $wins = [TcWinProbe.Winum]::Enumerate()
    foreach ($w in $wins) {
        $result.windows += [ordered]@{
            class = $w.ClassName
            title = $w.Title
            pid = $w.ProcessId
            tid = $w.ThreadId
        }
    }
} catch {
    Add-ErrorRow -Result $result -Where "window_enum" -Err $_
}

# 4. Named objects (\BaseNamedObjects) — best-effort, requires Sysinternals or fallback
# winobj.exe (Sysinternals) lists \BaseNamedObjects. If installed, capture its output.
$winobj = @(
    "C:\tcw\Sysinternals\winobj.exe",
    "C:\tcw\Sysinternals64\winobj.exe",
    "C:\tcw\winobj.exe",
    "C:\Tools\Sysinternals\winobj.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($winobj) {
    try {
        # winobj has a CLI mode: winobj.exe \BaseNamedObjects -accepteula
        $out = & $winobj "\BaseNamedObjects" 2>&1 | Out-String
        $result.named_objects = @($out -split "`n" | Where-Object { $_ -match "(?i)\b(tc|think|tcasr)" } | ForEach-Object { $_.Trim() })
        $result.machine.winobj_path = $winobj
    } catch {
        Add-ErrorRow -Result $result -Where "winobj" -Err $_
    }
} else {
    $result.machine.winobj_available = $false
}

# Verdict
$result.verdict.binary_count = $result.binaries.Count
$result.verdict.process_count = $result.processes.Count
$result.verdict.window_count = $result.windows.Count
$result.verdict.named_object_count = $result.named_objects.Count
$result.verdict.tcasr_running = ($result.processes.Count -gt 0)
$result.verdict.tcasr_on_disk = ($result.binaries.Count -gt 0)
if ($result.binaries.Count -gt 0) {
    $top = $result.binaries[0]
    $result.verdict.first_binary_path = $top.path
    $result.verdict.first_binary_version = $top.file_version
}

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
